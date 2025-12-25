import threading
import time
import random
import logging
import yaml
import sys
import os
from django.conf import settings

# 添加 federation_core 到 Python 路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEDERATION_CORE_PATH = os.path.join(BASE_DIR, 'federation_core')
if FEDERATION_CORE_PATH not in sys.path:
    sys.path.insert(0, FEDERATION_CORE_PATH)

# 移除全局logger定义，使用每个任务的独立logger

class DynamicFederation:
    """修改后的联邦学习任务类，初始参与者为0"""
    
    def __init__(self, task_id, task_name, config_path=None):
        # 如果没有提供配置文件路径，则使用任务特定的参数文件
        if config_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            core_dir = os.path.join(base_dir, 'federation_core')
            config_path = os.path.join(core_dir, f'saved_models/task_{task_id}', 'params.yaml')
        
        # 确保配置文件存在
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"参数文件不存在: {config_path}")
        
        # 加载配置
        with open(config_path, 'r', encoding='utf-8') as f:
            self.params = yaml.safe_load(f)
        
        # 初始化联邦学习环境
        current_time = str(int(time.time()))
        
        # 现在可以直接导入，因为路径已添加
        from federation_core.handle import Handle
        self.handle = Handle(current_time, self.params, task_id, task_name)
        
        # 使用Handle的logger作为任务专属logger
        self.logger = self.handle.logger
        
        # 加载数据和模型
        self.handle.load_data()
        self.handle.create_model()
        
        # 线程控制
        self.training_thread = None
        self.is_training = False
        self.training_paused = False
        self.task_id = task_id

        self._update_task_status('running')
        self._update_current_epoch(0)
        
        self.logger.info(f"联邦学习任务 {task_id} 初始化完成 - 模型:{self.params['model']}, 数据集:{self.params['type']}, 轮数:{self.params['epochs']}")

    def start_federation(self):
        """启动联邦学习系统"""
        self.logger.info(f"启动联邦学习任务 {self.task_id}...")  # 使用任务专属logger
        
        # 启动训练线程
        self.is_training = True
        self.training_thread = threading.Thread(target=self._training_loop)
        self.training_thread.daemon = True
        self.training_thread.start()
        
        self.logger.info(f"联邦训练线程 {self.task_id} 已启动")  # 使用任务专属logger

    def stop_federation(self):
        """停止联邦学习系统"""
        self.logger.info(f"正在停止联邦学习任务 {self.task_id}...")  # 使用任务专属logger
        self.is_training = False
        
        if self.training_thread:
            self.training_thread.join(timeout=10)
            
        self.logger.info(f"联邦学习任务 {self.task_id} 已停止")  # 使用任务专属logger

    def _training_loop(self):
        """训练循环 - 修改为非阻塞版本"""
        # 在训练线程中也修改工作目录
        original_cwd = os.getcwd()
        os.chdir(FEDERATION_CORE_PATH)
        
        try:
            last_check_time = 0
            check_interval = 5  # 检查间隔（秒）
            
            while self.is_training:
                current_time = time.time()
                
                # 只在达到检查间隔时执行检查，避免频繁循环
                if current_time - last_check_time < check_interval:
                    time.sleep(0.1)  # 短暂休眠，避免CPU占用过高
                    continue
                    
                last_check_time = current_time
                
                current_users = len(self.handle.namelist)
                    
                # 检查用户数量条件
                if current_users < 2:
                    if not self.training_paused:
                        self.logger.warning(f"任务 {self.task_id}: 当前用户数 {current_users} 少于2人，训练挂起")  # 使用任务专属logger
                        self.training_paused = True
                        # 更新数据库状态为暂停
                        self._update_task_status('paused')
                    continue
                
                if self.training_paused:
                    self.logger.info(f"任务 {self.task_id}: 当前用户数 {current_users} 达到要求，恢复训练")  # 使用任务专属logger
                    self.training_paused = False
                    # 更新数据库状态为运行中
                    self._update_task_status('running')
            
                # 执行联邦训练
                try:
                    self.logger.info(f"任务 {self.task_id}: 开始第 {self.handle.start_epoch} 轮联邦训练，当前用户数: {current_users}")  # 使用任务专属logger
                    from federation_core.algorithm import FedAvg
                    FedAvg(self.handle)
                    self.handle.start_epoch += 1
                    
                    # 更新数据库中的当前轮次
                    self._update_current_epoch(self.handle.start_epoch - 1)  # -1 因为已经递增了
                    
                    # 检查是否达到最大训练轮数
                    if self.handle.start_epoch > self.params['epochs']:
                        self.logger.info(f"任务 {self.task_id}: 达到最大训练轮数，停止训练")
                        self.is_training = False
                        # 执行股份/奖金分配
                        self._distribute_rewards_or_shares()
                        # 更新数据库状态为已完成
                        self._update_task_status('completed')
                        break
                        
                except Exception as e:
                    self.logger.error(f"任务 {self.task_id}: 训练过程中发生错误: {e}")  # 使用任务专属logger
                    # 错误时短暂休眠
                    time.sleep(1)
        finally:
            # 恢复原始工作目录
            os.chdir(original_cwd)

    def _update_task_status(self, status):
        """更新数据库中的任务状态"""
        try:
            from federation_app.models import FederationTask
            task = FederationTask.objects.get(task_id=self.task_id)
            task.status = status
            task.save()
            self.logger.debug(f"任务 {self.task_id} 状态更新为: {status}")  # 使用任务专属logger
        except Exception as e:
            self.logger.error(f"更新任务状态失败: {e}")  # 使用任务专属logger

    def _update_current_epoch(self, epoch):
        """更新数据库中的当前轮次"""
        try:
            from federation_app.models import FederationTask
            task = FederationTask.objects.get(task_id=self.task_id)
            task.current_epoch = epoch
            task.save()
            self.logger.debug(f"任务 {self.task_id} 当前轮次更新为: {epoch}")  # 使用任务专属logger
        except Exception as e:
            self.logger.error(f"更新当前轮次失败: {e}")  # 使用任务专属logger

    def _distribute_rewards_or_shares(self):
        """任务完成后分配股份或奖金"""
        try:
            from federation_app.models import FederationTask
            from federation_app.business_logic import ShareManagementService

            task = FederationTask.objects.get(task_id=self.task_id)

            # 获取最终贡献度数据
            contribution_data = self.handle.contribution_manager.get_user_final_ratios()

            if not contribution_data:
                self.logger.warning(f"任务 {self.task_id}: 没有贡献度数据，跳过分配")
                return

            # 转换为{user_id: contribution}格式
            user_contributions = {}
            for user_id_str, ratio in contribution_data.items():
                try:
                    user_id = int(user_id_str)
                    total_contribution = self.handle.contribution_manager.contribution_data.get(
                        'user_total_contributions', {}
                    ).get(str(user_id), 0)
                    user_contributions[user_id] = total_contribution
                except (ValueError, KeyError) as e:
                    self.logger.error(f"解析用户{user_id_str}贡献度失败: {e}")
                    continue

            # 根据支付模式执行不同的分配逻辑
            if task.payment_mode == 'shareholding':
                self.logger.info(f"任务 {self.task_id}: 开始分配股份")
                result = ShareManagementService.distribute_shares_by_contribution(
                    task, user_contributions
                )
                self.logger.info(f"任务 {self.task_id}: 股份分配完成，共{len(result)}个股东")

            elif task.payment_mode == 'reward':
                self.logger.info(f"任务 {self.task_id}: 开始分配奖金")
                result = ShareManagementService.distribute_rewards_by_contribution(
                    task, user_contributions
                )
                self.logger.info(f"任务 {self.task_id}: 奖金分配完成，共{len(result)}个受益人")

        except Exception as e:
            self.logger.error(f"任务 {self.task_id}: 分配股份/奖金失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    def get_status(self):
        """获取系统状态"""
        status = self.handle.get_status()
        status.update({
            'is_training': self.is_training,
            'training_paused': self.training_paused,
            'task_id': self.task_id
        })
        return status