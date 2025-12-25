import threading
import time
import logging
import yaml
from django.conf import settings
import os
from .models import FederationTask, TaskParticipant, TaskLog, GlobalAccuracy  # 添加导入

logger = logging.getLogger("logger")

class FederationTaskManager:
    """联邦任务管理器"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.tasks = {}
        return cls._instance
    
    def create_task(self, task_id, task_name, description="", model_architecture="r8",
                   dataset="CIFAR10", epochs=2000, reward_pool=0.00, payment_mode="shareholding",
                   usage_fee_per_request=0.50, creator=None):
        """创建新的联邦任务"""
        from .tasks import DynamicFederation

        if task_id in self.tasks:
            raise ValueError(f"任务 {task_id} 已存在")

        # 创建数据库记录
        task_obj = FederationTask.objects.create(
            task_id=task_id,
            task_name=task_name,
            description=description,
            model_architecture=model_architecture,
            dataset=dataset,
            epochs=epochs,
            reward_pool=reward_pool,
            total_epochs=epochs,
            payment_mode=payment_mode,
            usage_fee_per_request=usage_fee_per_request,
            creator=creator
        )
        
        # 生成动态参数文件
        params_path = self._generate_params_file(task_obj)
        
        # 创建联邦学习实例
        try:
            federation = DynamicFederation(task_id, task_name, params_path)
            self.tasks[task_id] = {
                'instance': federation,
                'object': task_obj,
                'thread': None
            }
            
            # 记录日志
            TaskLog.objects.create(
                task=task_obj,
                level='success',
                message=f"联邦任务 {task_name} 创建成功 - 模型:{model_architecture}, 数据集:{dataset}, 轮数:{epochs}, 奖金池:{reward_pool}"
            )
            
            return task_obj
        except Exception as e:
            task_obj.delete()
            raise e
    
    def _generate_params_file(self, task_obj):
        """为任务生成动态参数文件"""
        # 基础配置
        base_params = {
            'model': task_obj.model_architecture,
            'type': task_obj.dataset,
            'algorithm': 'FedAvg',
            'epochs': task_obj.epochs,
            'eta': 1,
            'local_epochs': 2,
            'batch_size': 128,
            'num_clients': 10,
            'number_of_total_participants': 100,
            'lr': 0.01,
            'lr_decay': True,
            'lr_decay_epoch': 1,
            'lr_decay_gamma': 0.998,
            'momentum': 0.9,
            'decay': 0.0005,
            'sampling_dirichlet': True,
            'dirichlet_alpha': 1,
            'is_poison': True,
            'poison_epochs': 6,
            'poison_lr': 0.005,
            'poison_rate': 0.5,
            'trigger_num': 1,
            'poison_client_num': 10,
            '0_poison_pattern': [[0, 0], [0, 1], [0, 2], [0, 3], [0, 6], [0, 7], [0, 8], [0, 9], [3, 0], [3, 1], [3, 2], [3, 3], [3, 6], [3, 7], [3, 8], [3, 9]],
            'defence_method': 'ours',
            'ours_standard': [0.50, 0.40, 0.30, 0.20],
            'seed': 1,
            'task_id': task_obj.task_id,
            'task_name': task_obj.task_name,
            'reward_pool': float(task_obj.reward_pool)
        }
        
        # 创建任务参数目录
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        core_dir = os.path.join(base_dir, 'federation_core')
        task_params_dir = os.path.join(core_dir, f'saved_models/task_{task_obj.task_id}')
        os.makedirs(task_params_dir, exist_ok=True)
        
        # 参数文件路径
        params_path = os.path.join(task_params_dir, 'params.yaml')
        
        # 写入参数文件
        with open(params_path, 'w', encoding='utf-8') as f:
            yaml.dump(base_params, f, default_flow_style=False, allow_unicode=True)
        
        return params_path
    
    def start_task(self, task_id):
        """启动联邦任务"""
        if task_id not in self.tasks:
            raise ValueError(f"任务 {task_id} 不存在")

        task_data = self.tasks[task_id]
        federation = task_data['instance']

        if task_data['thread'] and task_data['thread'].is_alive():
            raise ValueError(f"任务 {task_id} 已在运行中")

        # 更新数据库状态为running
        task_obj = task_data['object']
        task_obj.status = 'running'
        task_obj.save()

        # 启动任务线程
        thread = threading.Thread(target=federation.start_federation)
        thread.daemon = True
        thread.start()

        task_data['thread'] = thread

        TaskLog.objects.create(
            task=task_obj,
            level='success',
            message="联邦任务启动成功"
        )

        logger.info(f"任务 {task_id} 已启动，状态更新为 running")

    def add_user_to_task(self, task_id, user):
        """添加用户到任务（user是User对象）"""
        if task_id not in self.tasks:
            raise ValueError(f"任务 {task_id} 不存在")

        task_data = self.tasks[task_id]
        federation = task_data['instance']
        task_obj = task_data['object']

        # 添加到联邦学习实例
        success = federation.handle.add_user_to_federation(user.id)

        if success:
            # 创建参与者记录
            TaskParticipant.objects.get_or_create(
                task=task_obj,
                user=user,
                defaults={
                    'is_active': True
                }
            )

            # 更新活跃用户数
            current_users = len(federation.handle.namelist)
            task_obj.active_users = current_users

            # 立即检查并更新状态
            if task_obj.status == 'paused' and current_users >= 2:
                task_obj.status = 'running'
                federation.training_paused = False
                logger.info(f"任务 {task_id}: 用户加入后立即恢复训练状态")

            task_obj.save()

            TaskLog.objects.create(
                task=task_obj,
                level='success',
                message=f"用户 {user.username}(ID:{user.id}) 成功加入联邦任务，当前用户数: {current_users}"
            )
            return True
        else:
            TaskLog.objects.create(
                task=task_data['object'],
                level='warning',
                message=f"用户 {user.username}(ID:{user.id}) 加入联邦任务失败"
            )
            return False
    
    def remove_user_from_task(self, task_id, user):
        """从任务中移除用户（user是User对象）"""
        if task_id not in self.tasks:
            raise ValueError(f"任务 {task_id} 不存在")

        task_data = self.tasks[task_id]
        federation = task_data['instance']
        task_obj = task_data['object']

        # 从联邦学习实例移除
        success = federation.handle.remove_user_from_federation(user.id)

        if success:
            # 更新参与者状态
            participant = TaskParticipant.objects.filter(
                task=task_obj,
                user=user,
                is_active=True
            ).first()

            if participant:
                participant.is_active = False
                participant.save()

            # 更新活跃用户数
            current_users = len(federation.handle.namelist)
            task_obj.active_users = current_users

            # 立即检查并更新状态
            if task_obj.status == 'running' and current_users < 2:
                task_obj.status = 'paused'
                federation.training_paused = True
                logger.info(f"任务 {task_id}: 用户退出后立即暂停训练状态")
            
            task_obj.save()
            
            TaskLog.objects.create(
                task=task_obj,
                level='info',
                message=f"用户 {user_id} 已退出联邦任务，当前用户数: {current_users}"
            )
            return True
        else:
            TaskLog.objects.create(
                task=task_data['object'],
                level='warning',
                message=f"用户 {user_id} 退出联邦任务失败"
            )
            return False
    
    def get_task_status(self, task_id):
        """获取任务状态"""
        # 首先检查任务是否在内存中运行
        if task_id in self.tasks:
            task_data = self.tasks[task_id]
            federation = task_data['instance']

            status = federation.get_status()

            # 从数据库重新获取最新状态（使用 defer() 优化，但确保获取最新数据）
            from django.db import connection
            connection.close()  # 关闭可能存在的旧连接，强制获取新数据

            task_obj = FederationTask.objects.get(task_id=task_id)

            # 确定训练状态：如果数据库状态是 running 且没有暂停，就是进行中
            is_training_active = (task_obj.status == 'running' and
                                not federation.training_paused)

            status.update({
                'task_id': task_id,
                'task_name': task_obj.task_name,
                'status': task_obj.status,
                'current_epoch': task_obj.current_epoch,
                'training_paused': federation.training_paused,
                'is_training_active': is_training_active,  # 新增字段，表示训练是否活跃
                'is_running': True,  # 标记任务正在运行
                'created_at': task_obj.created_at.isoformat(),  # 添加创建时间
                'dataset': task_obj.dataset,  # 数据集
                'model_architecture': task_obj.model_architecture,  # 模型架构
                'total_epochs': task_obj.total_epochs,  # 总轮次
                'creator_id': task_obj.creator.id if task_obj.creator else None,  # 创建者ID
            })

            return status
        else:
            # 任务不在内存中，从数据库获取状态
            try:
                task_obj = FederationTask.objects.get(task_id=task_id)
                # 不在内存中的任务，如果状态是running，应显示为stopped
                display_status = task_obj.status if task_obj.status != 'running' else 'stopped'
                
                return {
                    'task_id': task_id,
                    'task_name': task_obj.task_name,
                    'status': display_status,  # 使用修正后的状态
                    'current_epoch': task_obj.current_epoch,
                    'active_users': task_obj.active_users,
                    'total_epochs': task_obj.total_epochs,
                    'training_paused': True,  # 不在运行的任务视为暂停
                    'is_training_active': False,  # 不在运行
                    'is_running': False,  # 标记任务不在运行
                    'description': task_obj.description,
                    'created_at': task_obj.created_at.isoformat(),
                    'dataset': task_obj.dataset,  # 数据集
                    'model_architecture': task_obj.model_architecture,  # 模型架构
                    'creator_id': task_obj.creator.id if task_obj.creator else None,  # 创建者ID
                }
            except FederationTask.DoesNotExist:
                raise ValueError(f"任务 {task_id} 不存在")
        
    def get_all_tasks_status(self):
        """获取所有任务状态"""
        status_list = []
        
        # 首先获取所有数据库中的任务
        all_tasks = FederationTask.objects.all()
        
        for task in all_tasks:
            try:
                status = self.get_task_status(task.task_id)
                status_list.append(status)
            except Exception as e:
                logger.error(f"获取任务 {task.task_id} 状态失败: {e}")
                status_list.append({
                    'task_id': task.task_id,
                    'task_name': task.task_name,
                    'status': 'error',
                    'error': str(e)
                })
        return status_list
    
    def get_task_accuracy_history(self, task_id):
        """获取任务的准确度历史记录"""
        try:
            task_obj = FederationTask.objects.get(task_id=task_id)
            accuracy_records = GlobalAccuracy.objects.filter(task=task_obj).order_by('epoch')
            
            return {
                'success': True,
                'task_id': task_id,
                'accuracy_history': [
                    {
                        'epoch': record.epoch,
                        'accuracy': record.accuracy,
                        'timestamp': record.created_at.isoformat()
                    }
                    for record in accuracy_records
                ]
            }
        except FederationTask.DoesNotExist:
            return {'success': False, 'message': f"任务 {task_id} 不存在"}
        except Exception as e:
            logger.error(f"获取准确度历史失败: {e}")
            return {'success': False, 'message': str(e)}

# 全局任务管理器实例
task_manager = FederationTaskManager()