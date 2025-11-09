import asyncio
import logging
import sqlite3
import os
import random
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest, JoinChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest, GetHistoryRequest, ImportChatInviteRequest
from telethon.tl.types import Channel, Chat
from config import USERBOT_API_ID, USERBOT_API_HASH, USERBOT_SESSION_FILE
from database import update_queue_status, save_check_result, get_pending_checks, get_userbot_result  # ДОБАВЛЕН ИМПОРТ

# Настройка логирования
logging.getLogger("telethon").setLevel(logging.WARNING)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class GroupAnalyzer:
    def __init__(self, client):
        self.client = client
    
    async def join_group(self, invite_link):
        """Присоединяемся к группе по ссылке - УНИВЕРСАЛЬНЫЙ МЕТОД"""
        try:
            logger.info(f"🔄 Пытаюсь присоединиться к группе: {invite_link}")
            
            # Метод 1: Пробуем получить entity и присоединиться
            try:
                entity = await self.client.get_entity(invite_link)
                await self.client(JoinChannelRequest(entity))
                logger.info(f"✅ Успешно присоединились (метод 1): {invite_link}")
                return True
            except Exception as e1:
                logger.warning(f"Метод 1 не сработал: {e1}")
            
            # Метод 2: Пробуем через ImportChatInviteRequest (для приватных ссылок)
            try:
                # Извлекаем хэш из ссылки
                if "t.me/+" in invite_link:
                    hash_part = invite_link.split("+")[1]
                    await self.client(ImportChatInviteRequest(hash_part))
                    logger.info(f"✅ Успешно присоединились (метод 2): {invite_link}")
                    return True
            except Exception as e2:
                logger.warning(f"Метод 2 не сработал: {e2}")
            
            # Метод 3: Пробуем старый метод (для старых версий Telethon)
            try:
                # Для каналов
                await self.client(JoinChannelRequest(invite_link))
                logger.info(f"✅ Успешно присоединились (метод 3): {invite_link}")
                return True
            except Exception as e3:
                logger.warning(f"Метод 3 не сработал: {e3}")
            
            logger.error(f"❌ Все методы присоединения не сработали для: {invite_link}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка присоединения к группе {invite_link}: {e}")
            return False
    
    async def leave_group(self, group_id):
        """Выходим из группы - УНИВЕРСАЛЬНЫЙ МЕТОД"""
        try:
            # Метод 1: Пробуем delete_dialog
            try:
                await self.client.delete_dialog(group_id)
                logger.info(f"✅ Успешно вышел из группы (метод 1): {group_id}")
                return True
            except Exception as e1:
                logger.warning(f"Метод 1 выхода не сработал: {e1}")
            
            # Метод 2: Пробуем получить entity и выйти
            try:
                entity = await self.client.get_entity(group_id)
                if isinstance(entity, Channel):
                    await self.client(LeaveChannelRequest(entity))
                logger.info(f"✅ Успешно вышел из группы (метод 2): {group_id}")
                return True
            except Exception as e2:
                logger.warning(f"Метод 2 выхода не сработал: {e2}")
            
            logger.error(f"❌ Все методы выхода не сработали для: {group_id}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка выхода из группы {group_id}: {e}")
            return False
    
    async def analyze_group(self, group_id):
        """Полный анализ группы через UserBot"""
        try:
            result = {
                'is_geo_group': False,
                'geo_reasons': [],
                'has_imported_messages': False,
                'has_imported_warning': False,
                'imported_status': 'normal',
                'imported_signs': [],
                'participants_count': 0,
                'group_type': 'unknown',
                'creation_date': None,
                'group_year': None,
                'group_month': None,
                'group_day': None,
                'message_count': 0,
                'total_messages_analyzed': 0,
                'username': None,
                'join_success': True
            }
            
            # Получаем сущность группы
            entity = await self.client.get_entity(group_id)
            
            # Базовая информация
            result['username'] = getattr(entity, 'username', None)
            result['title'] = getattr(entity, 'title', 'Unknown')
            result['group_id'] = group_id
            
            # Определяем год, месяц и день создания группы ПО САМОМУ ПЕРВОМУ СООБЩЕНИЮ
            date_result = await self._determine_group_date_by_first_message(entity)
            result.update(date_result)
            
            # Проверка на гео-группу
            geo_result = await self._check_geo_group(entity)
            result.update(geo_result)
            
            # Проверка на импортированные сообщения
            imported_result = await self._check_imported_messages_correct(entity)
            result.update(imported_result)
            
            # Получаем количество участников
            participants_result = await self._get_participants_count(entity)
            result.update(participants_result)
            
            # Анализ сообщений
            messages_result = await self._analyze_messages(entity)
            result.update(messages_result)
            
            logger.info(f"✅ UserBot анализ завершен для {result['title']}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа группы: {e}")
            current_date = datetime.now()
            return {
                'error': str(e),
                'is_geo_group': False,
                'has_imported_messages': False,
                'has_imported_warning': False,
                'imported_status': 'error',
                'imported_signs': [],
                'group_year': current_date.year,
                'group_month': current_date.month,
                'group_day': current_date.day,
                'join_success': False
            }
    
    async def _determine_group_date_by_first_message(self, entity):
        """Определяем дату создания группы по самому первому сообщению - САМЫЙ ТОЧНЫЙ МЕТОД"""
        try:
            result = {
                'group_year': None, 
                'group_month': None,
                'group_day': None,
                'creation_date': None,
                'creation_method': 'unknown'
            }
            
            # МЕТОД 1: Ищем самое первое сообщение в группе
            try:
                logger.info(f"🔍 Ищу самое первое сообщение в группе...")
                
                # Получаем сообщения в обратном порядке (от старых к новым)
                messages = await self.client.get_messages(
                    entity, 
                    limit=1, 
                    reverse=True,  # Это ключевой параметр - получаем самые старые сообщения
                    offset_date=None
                )
                
                if messages and len(messages) > 0:
                    first_message = messages[0]
                    if hasattr(first_message, 'date'):
                        message_date = first_message.date
                        result['group_year'] = message_date.year
                        result['group_month'] = message_date.month
                        result['group_day'] = message_date.day
                        result['creation_date'] = message_date.isoformat()
                        result['creation_method'] = 'first_message'
                        
                        logger.info(f"📅 Дата создания из первого сообщения: {result['group_day']}.{result['group_month']}.{result['group_year']}")
                        return result
                    else:
                        logger.warning("❌ Первое сообщение не имеет даты")
                else:
                    logger.warning("❌ Не найдено ни одного сообщения в группе")
                    
            except Exception as e:
                logger.warning(f"Не удалось получить первое сообщение: {e}")
            
            # МЕТОД 2: Пробуем получить несколько самых старых сообщений
            try:
                logger.info(f"🔍 Пробую получить историю сообщений...")
                
                # Получаем историю сообщений с начала
                messages = await self.client.get_messages(
                    entity, 
                    limit=10,  # Берем несколько сообщений для надежности
                    reverse=True,
                    offset_id=0
                )
                
                if messages and len(messages) > 0:
                    # Находим самое старое сообщение
                    oldest_message = None
                    for message in messages:
                        if hasattr(message, 'date'):
                            if oldest_message is None or message.date < oldest_message.date:
                                oldest_message = message
                    
                    if oldest_message:
                        message_date = oldest_message.date
                        result['group_year'] = message_date.year
                        result['group_month'] = message_date.month
                        result['group_day'] = message_date.day
                        result['creation_date'] = message_date.isoformat()
                        result['creation_method'] = 'oldest_message_found'
                        
                        logger.info(f"📅 Дата создания из самого старого найденного сообщения: {result['group_day']}.{result['group_month']}.{result['group_year']}")
                        return result
                        
            except Exception as e:
                logger.warning(f"Не удалось получить историю сообщений: {e}")
            
            # МЕТОД 3: Пробуем получить дату создания из полной информации о чате
            try:
                if isinstance(entity, Channel):
                    full_chat = await self.client(GetFullChannelRequest(entity))
                else:
                    full_chat = await self.client(GetFullChatRequest(entity.id))
                
                chat_full = full_chat.full_chat
                
                # Проверяем дату создания
                if hasattr(chat_full, 'date') and chat_full.date:
                    creation_date = chat_full.date
                    result['group_year'] = creation_date.year
                    result['group_month'] = creation_date.month
                    result['group_day'] = creation_date.day
                    result['creation_date'] = creation_date.isoformat()
                    result['creation_method'] = 'full_chat_date'
                    logger.info(f"📅 Дата создания из full_chat: {result['group_day']}.{result['group_month']}.{result['group_year']}")
                    return result
                    
            except Exception as e:
                logger.warning(f"Не удалось получить дату из full_chat: {e}")
            
            # МЕТОД 4: Пробуем получить дату из entity
            try:
                if hasattr(entity, 'date') and entity.date:
                    creation_date = entity.date
                    result['group_year'] = creation_date.year
                    result['group_month'] = creation_date.month
                    result['group_day'] = creation_date.day
                    result['creation_date'] = creation_date.isoformat()
                    result['creation_method'] = 'entity_date'
                    logger.info(f"📅 Дата создания из entity: {result['group_day']}.{result['group_month']}.{result['group_year']}")
                    return result
            except Exception as e:
                logger.warning(f"Не удалось получить дату из entity: {e}")
            
            # МЕТОД 5: Если все методы не сработали - используем текущую дату
            current_date = datetime.now()
            result['group_year'] = current_date.year
            result['group_month'] = current_date.month
            result['group_day'] = current_date.day
            result['creation_method'] = 'fallback_current_date'
            logger.warning("📅 Не удалось определить дату группы, использую текущую")
            
            logger.info(f"📅 Окончательная дата создания: {result['group_day']}.{result['group_month']}.{result['group_year']} (метод: {result['creation_method']})")
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка определения даты группы: {e}")
            current_date = datetime.now()
            return {
                'group_year': current_date.year,
                'group_month': current_date.month,
                'group_day': current_date.day,
                'creation_method': 'error_fallback',
                'error': str(e)
            }
    
    async def _check_geo_group(self, entity):
        """Проверка на гео-группу"""
        result = {'is_geo_group': False, 'geo_reasons': []}
        
        try:
            # Получаем полную информацию о чате
            if isinstance(entity, Channel):
                full_chat = await self.client(GetFullChannelRequest(entity))
            else:
                full_chat = await self.client(GetFullChatRequest(entity.id))
            
            chat_full = full_chat.full_chat
            
            # Проверяем гео-данные в полной информации чата
            if hasattr(chat_full, 'location') and chat_full.location:
                result['is_geo_group'] = True
                result['geo_reasons'].append("Привязана к местоположению")
            
            # Проверяем связанный чат
            if hasattr(chat_full, 'linked_chat_id') and chat_full.linked_chat_id:
                result['geo_reasons'].append("Есть связанный чат")
            
            # Проверяем различные атрибуты, которые могут указывать на гео-группу
            if hasattr(chat_full, 'address') and chat_full.address:
                result['is_geo_group'] = True
                result['geo_reasons'].append(f"Адрес: {chat_full.address}")
            
            # Косвенные признаки по названию
            title_lower = getattr(entity, 'title', '').lower()
            geo_keywords = ['город', 'city', 'москва', 'спб', 'киев', 'moscow', 'kiev']
            found_keywords = [kw for kw in geo_keywords if kw in title_lower]
            if found_keywords:
                result['geo_reasons'].append(f"Ключевые слова: {', '.join(found_keywords)}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки гео-группы: {e}")
            result['geo_reasons'].append(f"Ошибка проверки: {str(e)}")
            
        return result
    
    async def _check_imported_messages_correct(self, entity):
        """Проверяет наличие сообщений, импортированных из других мессенджеров."""
        try:
            messages = await self.client.get_messages(entity, limit=100)
            
            imported_messages_found = False
            imported_warning = False
            imported_signs = []
            saved_from_peer_count = 0
            imported_flag_count = 0
            total_messages = len(messages)

            for message in messages:
                if hasattr(message, 'fwd_from') and message.fwd_from:
                    fwd_from = message.fwd_from
                    
                    # КРИТИЧЕСКИЙ ПРИЗНАК: флаг imported (импорт из других мессенджеров)
                    if hasattr(fwd_from, 'imported') and fwd_from.imported:
                        imported_flag_count += 1
                        imported_messages_found = True
                        imported_signs.append("Критично: сообщения с флагом 'imported' (импорт из других мессенджеров)")
                    
                    # ПРЕДУПРЕЖДЕНИЕ: saved_from_peer (пересланные сообщения внутри Telegram)
                    if hasattr(fwd_from, 'saved_from_peer') and fwd_from.saved_from_peer:
                        saved_from_peer_count += 1

            # Анализируем saved_from_peer сообщения
            if saved_from_peer_count > 0:
                percentage = (saved_from_peer_count / total_messages) * 100
                if percentage > 40:  # Если больше 40% сообщений - пересланные
                    imported_warning = True
                    imported_signs.append(f"Предупреждение: много пересланных сообщений ({saved_from_peer_count}/{total_messages}, {percentage:.1f}%)")
                elif percentage > 20:  # Если 20-40% - умеренное количество
                    imported_warning = True
                    imported_signs.append(f"Предупреждение: умеренное количество пересланных сообщений ({saved_from_peer_count}/{total_messages}, {percentage:.1f}%)")
                else:
                    imported_signs.append(f"Норма: несколько пересланных сообщений ({saved_from_peer_count})")

            # Определяем общий статус
            if imported_messages_found:
                status = "critical"  # ❌ Критично
            elif imported_warning:
                status = "warning"   # ⚠️ Предупреждение
            else:
                status = "normal"    # ✅ Норма

            logger.info(f"🔍 Проверка импорта: статус={status}, saved_peer={saved_from_peer_count}, imported_flag={imported_flag_count}")
            
            return {
                'has_imported_messages': imported_messages_found,
                'has_imported_warning': imported_warning,
                'imported_status': status,
                'imported_signs': imported_signs,
                'saved_from_peer_count': saved_from_peer_count,
                'imported_flag_count': imported_flag_count,
                'total_messages_analyzed': total_messages
            }

        except Exception as e:
            logger.error(f"❌ Ошибка при проверке импортированных сообщений: {e}")
            return {
                'has_imported_messages': False,
                'has_imported_warning': False,
                'imported_status': 'error',
                'imported_signs': [f"Ошибка проверки: {str(e)}"]
            }
    
    async def _get_participants_count(self, entity):
        """Получаем количество участников"""
        try:
            participants = await self.client.get_participants(entity, limit=100)
            return {'participants_count': len(participants)}
        except Exception as e:
            logger.error(f"❌ Ошибка получения участников: {e}")
            return {'participants_count': 0}
    
    async def _analyze_messages(self, entity):
        """Анализ сообщений группы"""
        try:
            # Получаем больше сообщений для статистики
            messages = await self.client.get_messages(entity, limit=100)
            total_messages = len(messages)
            
            # Пробуем получить общее количество сообщений
            try:
                # Для каналов
                if isinstance(entity, Channel):
                    full_chat = await self.client(GetFullChannelRequest(entity))
                    message_count = getattr(full_chat.full_chat, 'participants_count', total_messages)
                else:
                    # Для групп
                    full_chat = await self.client(GetFullChatRequest(entity.id))
                    message_count = getattr(full_chat.full_chat, 'participants_count', total_messages)
            except:
                message_count = total_messages
            
            return {
                'message_count': message_count,
                'total_messages_analyzed': total_messages
            }
        except Exception as e:
            logger.error(f"❌ Ошибка анализа сообщений: {e}")
            return {
                'message_count': 0,
                'total_messages_analyzed': 0
            }

# Глобальная переменная для доступа к analyzer
analyzer = None

async def start_userbot():
    """Запуск UserBot с авторизацией по номеру телефона"""
    global analyzer
    
    client = TelegramClient(USERBOT_SESSION_FILE, USERBOT_API_ID, USERBOT_API_HASH)
    
    try:
        print("\n🔐 **АВТОРИЗАЦИЯ USERBOT** 🔐")
        print("=" * 40)
        
        # Запускаем клиент
        await client.start()
        
        # Если пользователь уже авторизован
        if await client.is_user_authorized():
            me = await client.get_me()
            logger.info(f"✅ UserBot уже авторизован как: {me.first_name} (@{me.username})")
            print(f"✅ Авторизован как: {me.first_name} (@{me.username})")
            analyzer = GroupAnalyzer(client)
            return client
        
        # Если не авторизован - запрашиваем номер
        print("\n📱 Введите номер телефона в международном формате:")
        print("Пример: +79123456789")
        
        phone = input("Номер телефона: ").strip()
        
        # Отправляем код
        await client.send_code_request(phone)
        print(f"\n📨 Код отправлен на номер: {phone}")
        
        # Запрашиваем код
        code = input("Введите код из Telegram: ").strip()
        
        # Авторизуемся
        await client.sign_in(phone, code)
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        logger.info(f"✅ UserBot успешно авторизован как: {me.first_name} (@{me.username})")
        print(f"✅ Успешная авторизация: {me.first_name} (@{me.username})")
        
        analyzer = GroupAnalyzer(client)
        return client
        
    except Exception as e:
        logger.error(f"❌ Ошибка авторизации UserBot: {e}")
        print(f"❌ Ошибка авторизации: {e}")
        return None

async def process_pending_checks():
    """Обработка ожидающих проверок"""
    global analyzer
    
    while True:
        try:
            pending_checks = get_pending_checks()
            
            if pending_checks:
                print(f"📋 Найдено групп в очереди: {len(pending_checks)}")
            
            for check in pending_checks:
                queue_id, group_id, group_title, user_id, invite_link, status, created_at = check
                
                # Проверяем, нет ли уже результатов для этой группы
                existing_result = get_userbot_result(group_id)
                if existing_result:
                    print(f"⏩ Пропускаем группу {group_title} - уже есть результаты")
                    update_queue_status(queue_id, "userbot_done")
                    continue
                
                print(f"🔄 Обрабатываю группу: {group_title}")
                logger.info(f"🔄 Обрабатываем группу: {group_title}")
                
                # Обновляем статус
                update_queue_status(queue_id, "processing")
                
                # Присоединяемся к группе
                print(f"🔗 Пытаюсь присоединиться по ссылке: {invite_link}")
                join_success = await analyzer.join_group(invite_link)
                
                if join_success:
                    print(f"✅ Успешно присоединился к группе: {group_title}")
                    
                    # Ждем немного перед анализом
                    await asyncio.sleep(3)
                    
                    # Анализируем группу
                    print(f"🔍 Начинаю анализ группы: {group_title}")
                    userbot_result = await analyzer.analyze_group(group_id)
                    
                    # Сохраняем результат
                    save_check_result(
                        group_id=group_id,
                        group_title=group_title,
                        user_id=user_id,
                        bot_result={},
                        userbot_result=userbot_result,
                        final_result=False,
                        issues=""
                    )
                    
                    # Обновляем статус
                    update_queue_status(queue_id, "userbot_done")
                    
                    print(f"✅ Анализ завершен: {group_title}")
                    logger.info(f"✅ UserBot завершил проверку группы: {group_title}")
                    
                    # Ждем перед выходом
                    await asyncio.sleep(2)
                    
                    # После проверки выходим из группы
                    try:
                        await analyzer.leave_group(group_id)
                        print(f"🚪 Вышел из группы: {group_title}")
                        logger.info(f"✅ UserBot вышел из группы после проверки: {group_title}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка выхода из группы после проверки: {e}")
                        print(f"⚠️ Не удалось выйти из группы: {e}")
                        
                else:
                    # Если не удалось присоединиться
                    update_queue_status(queue_id, "failed")
                    logger.error(f"❌ Не удалось присоединиться к группе: {group_title}")
                    print(f"❌ Не удалось присоединиться к группе: {group_title}")
            
            # Случайная задержка между проверками
            delay = random.uniform(10, 20)
            print(f"⏳ Следующая проверка через {delay:.1f} секунд...")
            await asyncio.sleep(delay)
            
        except Exception as e:
            logger.error(f"❌ Ошибка в процессе проверки: {e}")
            print(f"❌ Ошибка: {e}")
            await asyncio.sleep(10)

async def main_userbot():
    """Основная функция UserBot"""
    global analyzer
    
    print("🚀 ЗАПУСК USERBOT")
    print("=" * 40)
    
    client = await start_userbot()
    if client and analyzer:
        print("\n✅ UserBot успешно запущен и авторизован!")
        print("🔄 Начинаю обработку очереди проверок...")
        print("💡 UserBot будет автоматически проверять группы из очереди")
        print("⏳ Ожидайте добавления групп в очередь через основного бота\n")
        
        await process_pending_checks()
    else:
        print("\n❌ Не удалось запустить UserBot!")
        print("💡 Проверьте:")
        print("   - API_ID и API_HASH в config.py")
        print("   - Правильность введенного номера телефона")
        print("   - Правильность кода подтверждения")

if __name__ == "__main__":
    try:
        asyncio.run(main_userbot())
    except KeyboardInterrupt:
        print("\n\n👋 UserBot остановлен пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
