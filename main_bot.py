import asyncio
import logging
import aiosqlite
import time
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    Bot,
    ChatMemberAdministrator
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters, 
    ContextTypes
)
from config import BOT_TOKEN, ADMIN_ID, WEB_CHECK_MIN_DIFF, MAX_WAIT_TIME
from database import init_db, add_to_queue, update_queue_status, save_check_result, get_userbot_result, is_check_complete
from sync_manager import sync_manager


logging.getLogger("httpx").setLevel(logging.WARNING)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# база данных

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    try:
        user = update.effective_user
        
        welcome_text = (
            "🤖 Добро пожаловать в бота-оценщика групп!\n\n"
            "Я проведу полную проверку вашей Telegram группы:\n"
            "• Проверка прав и веб-анализ\n"
            "• UserBot анализ (гео-данные, импортированные сообщения)\n"
            "• Определение даты создания группы\n"
            "• Статистика сообщений и участников\n"
            "• Полный отчет о группе\n\n"
            "Как использовать:\n"
            "1. Добавьте меня в вашу группу\n"
            "2. Сделайте администратором\n"
            "3. Я автоматически начну проверку\n\n"
            "После проверки вы получите подробный отчет!\n\n"
            "Команды:\n"
            "/start - показать это сообщение\n"
            "/otkat <group_id> - выйти из группы (только для администратора)"
        )
        
        await update.message.reply_text(welcome_text)
        
    except Exception as e:
        logger.error(f"Ошибка отправки приветственного сообщения: {e}")
        await update.message.reply_text("🤖 Бот-оценщик групп активирован! Добавьте меня в группу и сделайте администратором для начала проверки.")

async def otkat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /otkat для выхода из группы"""
    user_id = update.effective_user.id
    
   
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Эта команда только для администратора!")
        return
    
    try:
       
        if not context.args:
            await update.message.reply_text("❌ Укажите ID группы: /otkat <group_id>")
            return
        
        group_id = int(context.args[0])
        
        await update.message.reply_text(f"🔄 Команда на выход из группы {group_id} принята. UserBot обработает запрос.")
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат ID группы. Пример: /otkat -1001234567890")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def check_bot_admin_rights(bot, chat_id, max_attempts=30):
    """Цикл проверки прав бота в группе"""
    for attempt in range(max_attempts):
        try:
            bot_member = await bot.get_chat_member(chat_id, bot.id)
            
            if isinstance(bot_member, ChatMemberAdministrator):
                logger.info(f"✅ Бот получил права администратора в чате {chat_id}")
                return True, bot_member
            
            logger.info(f"🕐 Попытка {attempt + 1}: Бот еще не администратор в чате {chat_id}")
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки прав в чате {chat_id}: {e}")
            await asyncio.sleep(2)
    
    return False, None

async def perform_web_check(bot, chat_id):
    """Веб-проверка: разница между ID сообщений"""
    try:
       
        test_message = await bot.send_message(
            chat_id=chat_id,
            text="⚡ Проверка сообщений..."
        )
        latest_message_id = test_message.message_id
        
       
        messages = []
        try:
           
            for i in range(10):
                try:
                    
                    message = await bot.get_messages(chat_id, offset=i, limit=1)
                    if message:
                        messages.extend(message)
                except:
                    break
        except Exception as e:
            logger.error(f"Ошибка получения истории сообщений: {e}")
        
      
        oldest_message_id = messages[-1].message_id if messages else 1
        
     
        message_id_diff = latest_message_id - oldest_message_id
        
        
        try:
            await bot.delete_message(chat_id=chat_id, message_id=latest_message_id)
        except:
            pass
        
        check_passed = message_id_diff > WEB_CHECK_MIN_DIFF
        
        logger.info(f"🌐 Веб-проверка: latest_id={latest_message_id}, oldest_id={oldest_message_id}, diff={message_id_diff}, passed={check_passed}")
        
        return {
            'message_id_diff': message_id_diff,
            'latest_message_id': latest_message_id,
            'oldest_message_id': oldest_message_id,
            'check_passed': check_passed,
            'min_required_diff': WEB_CHECK_MIN_DIFF
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка веб-проверки: {e}")
        return {
            'message_id_diff': 0, 
            'check_passed': False,
            'error': str(e)
        }

async def check_geo_by_name(chat_title):
    """Проверка на гео-группу по названию (резервный метод)"""
    geo_keywords = [
        'город', 'city', 'москва', 'спб', 'киев', 'moscow', 'kiev', 'питер',
        'санкт-петербург', 'минск', 'казахстан', 'украина', 'россия', 'russia',
        'ukraine', 'беларусь', 'belarus', 'казань', 'новосибирск', 'екатеринбург'
    ]
    
    title_lower = chat_title.lower()
    found_keywords = [kw for kw in geo_keywords if kw in title_lower]
    is_geo = len(found_keywords) > 0
    
    return {
        'is_geo_by_name': is_geo,
        'geo_keywords_found': found_keywords
    }

async def create_invite_link(bot, chat_id):
    """Создаем invite link для UserBot с проверкой"""
    try:
        
        try:
            await bot.get_chat(chat_id)
        except Exception as e:
            logger.error(f"❌ Бот не имеет доступа к группе {chat_id}: {e}")
            return None
        
      
        invite_link = await bot.create_chat_invite_link(
            chat_id=chat_id,
            creates_join_request=False,
            name="UserBot Access",
            expire_date=None,  # Бессрочная
            member_limit=None  # Без ограничений
        )
        
        logger.info(f"🔗 Создана пригласительная ссылка для чата {chat_id}: {invite_link.invite_link}")
        return invite_link.invite_link
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания invite link: {e}")
        return None

async def handle_bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик добавления бота в группу"""
    message = update.message
    chat = message.chat
    user = message.from_user
    
    if message.new_chat_members:
        for member in message.new_chat_members:
            if member.id == context.bot.id:
                logger.info(f"🤖 Бот добавлен в группу {chat.id} пользователем {user.id}")
                
                welcome_text = (
                    "👋 Бот-оценщик активирован!\n\n"
                    "🔄 Проверяю права администратора...\n"
                    "⏳ Ожидайте начала полной проверки."
                )
                
                await message.reply_text(welcome_text)
                
                
                asyncio.create_task(
                    full_group_analysis(context.bot, chat, user.id)
                )

async def wait_for_userbot_completion(group_id, timeout=300):
    """Ожидаем завершения проверки UserBot"""
    start_time = time.time()
    logger.info(f"⏳ Ожидаю завершения UserBot проверки для группы {group_id}")
    
    while (time.time() - start_time) < timeout:
      
        result = get_userbot_result(group_id)
        
        if result is not None:
            logger.info(f"✅ UserBot завершил проверку группы {group_id}")
            return result
        
      
        await asyncio.sleep(5)
    
    logger.warning(f"⏰ Таймаут ожидания UserBot для группы {group_id}")
    return None

async def full_group_analysis(bot, chat, user_id):
    """Полный анализ группы"""
    try:
       
        await bot.send_message(chat.id, "🔐 Проверяю права администратора...")
        is_admin, bot_member = await check_bot_admin_rights(bot, chat.id)
        
        if not is_admin:
            await bot.send_message(chat.id, "❌ Не предоставлены права администратора!\n\nПожалуйста, сделайте бота администратором для продолжения проверки.")
            return
        
        await bot.send_message(chat.id, "✅ Права администратора получены!")
        
  
        await bot.send_message(chat.id, "🔗 Создаю приглашение для углубленного анализа...")
        invite_link = await create_invite_link(bot, chat.id)
        
        if not invite_link:
            await bot.send_message(chat.id, "❌ Не удалось создать пригласительную ссылку!\n\nПроверьте права бота.")
            return
        
      
        queue_id = add_to_queue(chat.id, chat.title, user_id, invite_link)
        logger.info(f"📝 Группа {chat.title} добавлена в очередь (ID: {queue_id})")
        
        # 4. Проводим веб-проверку
        await bot.send_message(chat.id, "🌐 Провожу веб-анализ...")
        web_check_result = await perform_web_check(bot, chat.id)
        
     
        geo_check_result = await check_geo_by_name(chat.title)
        
       
        bot_result = {
            'web_check': web_check_result,
            'geo_check': geo_check_result,
            'chat_info': {
                'title': chat.title,
                'id': chat.id,
                'type': chat.type
            },
            'timestamp': str(time.time())
        }
        
  
        await bot.send_message(chat.id, "🤖 Ожидаю результаты углубленного анализа...\n\nЭто может занять несколько минут.")
        logger.info(f"⏳ Ожидаю UserBot для группы {chat.id}")
        
       
        userbot_result = await wait_for_userbot_completion(chat.id)
        
        if userbot_result is None:
            await bot.send_message(chat.id, "❌ UserBot не ответил вовремя.\n\nПопробуйте добавить бота в группу позже.")
            return
        
     
        await bot.send_message(chat.id, "📊 Формирую отчет...")
        final_report = await generate_final_report(bot_result, userbot_result)
        
        # 9. Отправляем отчет  await send_final_report(bot, chat.id, user_id, final_report)
        
        
        issues = await identify_issues(bot_result, userbot_result)
        final_result = len(issues) == 0
        
        save_check_result(
            group_id=chat.id,
            group_title=chat.title,
            user_id=user_id,
            bot_result=bot_result,
            userbot_result=userbot_result,
            final_result=final_result,
            issues=", ".join(issues)
        )
        
        logger.info(f"✅ Полная проверка группы {chat.title} завершена")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в полном анализе группы: {e}")
        await bot.send_message(chat.id, f"❌ Произошла ошибка при анализе:\n\n{str(e)}")

async def generate_final_report(bot_result, userbot_result):
    """Генерируем финальный отчет"""
    report = "📊 ПОЛНЫЙ ОТЧЕТ О ПРОВЕРКЕ\n\n"
    

    report += "🤖 Результаты основного бота:\n"
    
    web_check = bot_result['web_check']
    report += f"• Веб-проверка (ID сообщений): {web_check['message_id_diff']} "
    report += "✅ ПРОШЛА\n" if web_check['check_passed'] else f"❌ НЕ ПРОШЛА (минимум {web_check.get('min_required_diff', 50)})\n"
    
    geo_check = bot_result['geo_check']
    if geo_check['is_geo_by_name']:
        report += f"• Гео-признаки в названии: {', '.join(geo_check['geo_keywords_found'])} ⚠️\n"
    else:
        report += "• Гео-признаки в названии: ✅ НЕТ\n"
    
    # Результаты UserBot
    report += "\n🔍 Результаты углубленного анализа:\n"
    
    if userbot_result is None:
        report += "• UserBot: ❌ ДАННЫЕ НЕ ПОЛУЧЕНЫ\n"
    else:
       
        if userbot_result.get('group_year'):
            month_names = {
                1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
                5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август', 
                9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
            }
            month_name = month_names.get(userbot_result.get('group_month'), 'Неизвестно')
            day = userbot_result.get('group_day', '?')
            year = userbot_result['group_year']
            
            report += f"• Дата создания: {day} {month_name} {year} "
            method = userbot_result.get('creation_method', 'unknown')
            if method == 'first_message':
                report += "✅ \n"
            elif method in ['full_chat_date', 'entity_date']:
                report += "✅ \n"
            elif method == 'oldest_message_found':
                report += "📅 (по найденным сообщениям)\n"
            else:
                report += "⚡ (оценочная)\n"
        
     
        report += f"• Гео-группа: {'✅ НЕТ' if not userbot_result.get('is_geo_group') else '❌ ДА'}\n"
        if userbot_result.get('geo_reasons'):
            report += f"• Причины: {', '.join(userbot_result['geo_reasons'])}\n"
        
    
        imported_status = userbot_result.get('imported_status', 'normal')
        if imported_status == 'critical':
            report += "• Импортированные сообщения: ❌ КРИТИЧЕСКИЕ ПРИЗНАКИ\n"
        elif imported_status == 'warning':
            report += "• Импортированные сообщения: ⚠️ ПРЕДУПРЕЖДЕНИЕ\n"
        else:
            report += "• Импортированные сообщения: ✅ НОРМА\n"
            
        if userbot_result.get('imported_signs'):
        
            signs_to_show = userbot_result['imported_signs'][:2]
            for sign in signs_to_show:
                if 'Критично:' in sign:
                    report += f"  ❌ {sign.replace('Критично: ', '')}\n"
                elif 'Предупреждение:' in sign:
                    report += f"  ⚠️ {sign.replace('Предупреждение: ', '')}\n"
                elif 'Норма:' in sign:
                    report += f"  ✅ {sign.replace('Норма: ', '')}\n"
                else:
                    report += f"  • {sign}\n"
        
     
        participants = userbot_result.get('participants_count', 'N/A')
        total_messages = userbot_result.get('message_count', 'N/A')
        analyzed_messages = userbot_result.get('total_messages_analyzed', 'N/A')
        
        report += f"• Участников: {participants}\n"
        report += f"• Всего сообщений: {total_messages}\n"
        report += f"• Проанализировано: {analyzed_messages}\n"
        
      
        if userbot_result.get('saved_from_peer_count') is not None:
            saved_count = userbot_result['saved_from_peer_count']
            total_analyzed = userbot_result.get('total_messages_analyzed', 0)
            if total_analyzed > 0:
                percentage = (saved_count / total_analyzed) * 100
                report += f"• Пересланных сообщений: {saved_count} ({percentage:.1f}%)\n"
    
    # Итог
    issues = await identify_issues(bot_result, userbot_result)
    if not issues:
        report += "\n🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!\n"
        report += "Группа соответствует требованиям."
    else:
        report += f"\n📋 РЕЗУЛЬТАТ ПРОВЕРКИ:\n"
        
        
        critical_issues = [issue for issue in issues if '❌' in issue or 'КРИТИЧЕСКИЕ' in issue]
        warning_issues = [issue for issue in issues if '⚠️' in issue or 'ПРЕДУПРЕЖДЕНИЕ' in issue]
        other_issues = [issue for issue in issues if issue not in critical_issues + warning_issues]
        
        if critical_issues:
            report += "\n❌ КРИТИЧЕСКИЕ ПРОБЛЕМЫ:\n"
            for issue in critical_issues:
                report += f"• {issue.replace('❌ ', '').replace('КРИТИЧЕСКИЕ: ', '')}\n"
        
        if warning_issues:
            report += "\n⚠️ ВОЗМОЖНЫЕ ПРОБЛЕМЫ:\n"
            for issue in warning_issues:
                report += f"• {issue.replace('⚠️ ', '').replace('ПРЕДУПРЕЖДЕНИЕ: ', '')}\n"
        
        if other_issues:
            report += "\n📝 ЗАМЕЧАНИЯ:\n"
            for issue in other_issues:
                report += f"• {issue}\n"
    
    return report

async def identify_issues(bot_result, userbot_result):
    """Определяем проблемы с градацией по критичности"""
    issues = []
    

    if not bot_result['web_check']['check_passed']:
        diff = bot_result['web_check']['message_id_diff']
        min_diff = bot_result['web_check'].get('min_required_diff', 50)
        issues.append(f"❌ Малая разница ID сообщений ({diff}, требуется {min_diff}+)")
    
  
    if bot_result['geo_check']['is_geo_by_name']:
        issues.append(f"⚠️ Гео-слова: {', '.join(bot_result['geo_check']['geo_keywords_found'])}")
    
  
    if userbot_result and userbot_result.get('is_geo_group'):
        issues.append("❌ ГЕО-чат")
    
 
    if userbot_result:
        imported_status = userbot_result.get('imported_status', 'normal')
        if imported_status == 'critical':
            issues.append("❌ КРИТИЧЕСКИЕ: Обнаружены импортированные сообщения из других мессенджеров")
        elif imported_status == 'warning':
            issues.append("⚠️ ПРЕДУПРЕЖДЕНИЕ: Много пересланных сообщений внутри Telegram")
    
    # Ошибка UserBot
    if userbot_result is None:
        issues.append("❌ UserBot не завершил проверку")
    
    return issues

async def send_final_report(bot, chat_id, user_id, report):
    """Отправляем финальный отчет"""
    try:
        # В группу
        await bot.send_message(
            chat_id=chat_id,
            text=report
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки отчета: {e}")
 
        try:
            parts = [report[i:i+4000] for i in range(0, len(report), 4000)]
            for part in parts:
                await bot.send_message(chat_id=chat_id, text=part)
        except Exception as e2:
            logger.error(f"❌ Не удалось отправить отчет даже частями: {e2}")
        

    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"📋 Отчет по группе завершен!\n\n{report}"
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить отчет в ЛС пользователю {user_id}: {e}")

def main():
    """Запуск основного бота"""
    application = Application.builder().token(BOT_TOKEN).build()
    

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("otkat", otkat_command))
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS, 
        handle_bot_added_to_group
    ))
    
    print("🤖 Основной бот запущен!")
    print("💡 Добавьте бота в группу для начала проверки")
    print("🔧 Убедитесь, что UserBot также запущен")
    print("🔗 Команда /otkat <group_id> - выход из группы")
    
    application.run_polling()

if __name__ == "__main__":
    main()
