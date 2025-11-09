import asyncio
import time
import logging
from database import get_pending_checks, update_queue_status, save_check_result, get_userbot_result

logger = logging.getLogger(__name__)

class SyncManager:
    def __init__(self):
        self.pending_groups = {}
        self.callbacks = {}
    
    def register_callback(self, group_id, callback):
        """Регистрируем callback для уведомления о готовности результатов"""
        self.callbacks[group_id] = callback
        logger.info(f"📞 Зарегистрирован callback для группы {group_id}")
    
    async def wait_for_userbot_result(self, group_id, timeout=300):
        """Ожидаем результаты от UserBot с улучшенной синхронизацией"""
        start_time = time.time()
        check_attempts = 0
        
        logger.info(f"⏳ Ожидаю результаты UserBot для группы {group_id}...")
        
        while (time.time() - start_time) < timeout:
            check_attempts += 1
            
            # Проверяем базу данных на наличие результатов
            result = get_userbot_result(group_id)
            
            if result and result.get('join_success') is not None:
                logger.info(f"✅ Получены результаты UserBot для группы {group_id} (попытка {check_attempts})")
                
                # Вызываем callback если зарегистрирован
                if group_id in self.callbacks:
                    logger.info(f"📞 Вызываю callback для группы {group_id}")
                    try:
                        await self.callbacks[group_id](result)
                    except Exception as e:
                        logger.error(f"❌ Ошибка в callback для группы {group_id}: {e}")
                    finally:
                        del self.callbacks[group_id]
                
                return result
            
            # Если результатов еще нет, ждем
            wait_time = min(5, (timeout - (time.time() - start_time)) / 2)
            if wait_time > 0:
                logger.info(f"🕐 Результатов еще нет, жду {wait_time:.1f} сек... (попытка {check_attempts})")
                await asyncio.sleep(wait_time)
        
        logger.warning(f"⏰ Таймаут ожидания UserBot для группы {group_id} после {check_attempts} попыток")
        
        # Удаляем callback при таймауте
        if group_id in self.callbacks:
            del self.callbacks[group_id]
            
        return {
            'timeout': True,
            'error': f'UserBot не ответил в течение {timeout} секунд'
        }

# Глобальный менеджер синхронизации
sync_manager = SyncManager()
