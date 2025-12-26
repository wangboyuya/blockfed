import os
import json
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# 设置 Django 环境
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'federation_platform.settings')
django.setup()

from federation_app.blockchain_utils import sync_contribution_to_chain
from federation_app.models import FederationTask

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class ModelUpdateHandler(FileSystemEventHandler):
    """同时处理文件夹创建和文件修改的处理器"""
    
    def on_created(self, event):
        """逻辑1：保留原有功能 - 监听新文件夹创建"""
        if event.is_directory:
            folder_path = event.src_path
            folder_name = os.path.basename(folder_path)
            logger.info(f"✨ 检测到新任务文件夹: {folder_name}")
            self._check_and_process(folder_path, folder_name)

    def on_modified(self, event):
        """逻辑2：新增功能 - 监听现有 contribution_records.json 的变化"""
        if not event.is_directory:
            file_path = event.src_path
            file_name = os.path.basename(file_path)
            
            if file_name == "contribution_records.json":
                folder_path = os.path.dirname(file_path)
                folder_name = os.path.basename(folder_path)
                logger.info(f"🔄 检测到文件更新: {file_path}")
                # 稍微等待文件写入完成，防止读取冲突
                time.sleep(0.5) 
                self.process_contribution(folder_name, file_path)

    def _check_and_process(self, folder_path, folder_name):
        """辅助方法：新文件夹创建后等待 JSON 文件出现"""
        record_file = os.path.join(folder_path, "contribution_records.json")
        for _ in range(30):
            if os.path.exists(record_file):
                self.process_contribution(folder_name, record_file)
                break
            time.sleep(1)

    def process_contribution(self, folder_name, file_path):
        """核心解析与上链逻辑"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            contributions = data.get("user_total_contributions")
            if not contributions:
                return

            # 解析 Task ID (取文件夹名第一个下划线前的部分)
            # 例如 "1_TEST" -> "1"
            task_id = folder_name.split('_')[0] 
            
            logger.info(f"📢 正在同步任务 {task_id} 的最新贡献度至区块链...")
            
            # 使用文件夹名作为指纹，或者使用时间戳
            model_hash = f"hash_{folder_name}_updated_{int(time.time())}"
            
            # 调用你之前的上链函数
            # 由于合约中加入了 delete task.participants，这步操作会覆盖旧数据
            success = sync_contribution_to_chain(task_id, contributions, model_hash)
            
            if success:
                logger.info(f"✅ 任务 {task_id} 链上数据已更新成功")
            else:
                logger.error(f"❌ 任务 {task_id} 链上更新失败")

        except Exception as e:
            logger.error(f"处理任务 {folder_name} 时发生错误: {e}")

if __name__ == "__main__":
    WATCH_PATH = os.path.join(os.getcwd(), "federation_core", "saved_models")
    
    if not os.path.exists(WATCH_PATH):
        os.makedirs(WATCH_PATH)

    event_handler = ModelUpdateHandler()
    observer = Observer()
    # 关键修改：recursive=True 开启递归监控，监听子目录内文件的变化
    observer.schedule(event_handler, WATCH_PATH, recursive=True)
    
    logger.info(f"🚀 增强版监控启动，递归监听: {WATCH_PATH}")
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()