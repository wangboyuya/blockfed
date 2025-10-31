# main_dynamic.py
import threading
import time
import random
import logging
import yaml
from handle import Handle
from algorithm import FedAvg


# 配置主进程logger
def setup_main_logger():
    logger = logging.getLogger("server_main")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    console_handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


logger = setup_main_logger()


class DynamicFederation:
    def __init__(self, config_path='cifar_params.yaml'):
        with open(config_path, 'r') as f:
            self.params = yaml.safe_load(f)

        current_time = str(int(time.time()))
        self.handle = Handle(current_time, self.params, "dynamic_federation", "dynamic_task")

        self.handle.load_data()
        self.handle.create_model()

        self.training_thread = None
        self.user_management_thread = None
        self.is_training = False
        self.is_user_management = False
        self.training_paused = False

        logger.info("动态联邦学习环境初始化完成")

    def start_federation(self):
        """启动联邦学习系统"""
        logger.info("启动动态联邦学习系统...")

        self.is_training = True
        self.training_thread = threading.Thread(target=self._training_loop)
        self.training_thread.daemon = True
        self.training_thread.start()

        self.is_user_management = True
        self.user_management_thread = threading.Thread(target=self._user_management_loop)
        self.user_management_thread.daemon = True
        self.user_management_thread.start()

        logger.info("联邦训练和用户管理线程已启动")

    def stop_federation(self):
        """停止联邦学习系统"""
        logger.info("正在停止联邦学习系统...")

        self.is_training = False
        self.is_user_management = False

        if self.training_thread:
            self.training_thread.join(timeout=10)
        if self.user_management_thread:
            self.user_management_thread.join(timeout=10)

        # 新增：任务结束时的收益分配计算
        try:
            final_ratios = self.handle.get_final_reward_distribution()
            summary = self.handle.get_contribution_summary()

            logger.info("=== 任务收益分配结果 ===")
            logger.info(f"总训练轮次: {summary['total_rounds']}")
            logger.info(f"参与用户数: {summary['total_users']}")
            logger.info("各用户收益分配比例:")
            for user_id, ratio in final_ratios.items():
                logger.info(f"  用户 {user_id}: {ratio:.4f} ({ratio * 100:.2f}%)")

        except Exception as e:
            logger.error(f"收益分配计算失败: {e}")

        logger.info("联邦学习系统已停止")

    def _training_loop(self):
        """训练循环"""
        while self.is_training:
            current_users = len(self.handle.namelist)

            if current_users < 2:
                if not self.training_paused:
                    logger.warning(f"当前用户数 {current_users} 少于2人，训练挂起")
                    self.training_paused = True
                time.sleep(5)
                continue

            if self.training_paused:
                logger.info(f"当前用户数 {current_users} 达到要求，恢复训练")
                self.training_paused = False

            try:
                logger.info(f"开始第 {self.handle.start_epoch} 轮联邦训练，当前用户数: {current_users}")
                FedAvg(self.handle)
                self.handle.start_epoch += 1

                if self.handle.start_epoch > self.params['epochs']:
                    logger.info("达到最大训练轮数，停止训练")
                    self.is_training = False
                    break

            except Exception as e:
                logger.error(f"训练过程中发生错误: {e}")
                time.sleep(10)

    def _user_management_loop(self):
        """用户管理循环"""
        check_interval = 10

        self._add_initial_users()

        while self.is_user_management:
            try:
                status = self.handle.get_status()
                current_users = status["active_users"]

                if current_users < 9 and random.random() < 0.4:
                    self.handle.add_random_user()

                if current_users > 3 and random.random() < 0.3:
                    self.handle.remove_random_user()

                logger.info(f"用户管理检查完成 - 活跃用户: {current_users}, 可用用户: {status['available_users']}")

            except Exception as e:
                logger.error(f"用户管理过程中发生错误: {e}")

            time.sleep(check_interval)

    def _add_initial_users(self):
        """初始添加几个用户"""
        initial_users_count = 6
        for _ in range(initial_users_count):
            if not self.handle.add_random_user():
                break
        logger.info(f"初始添加了 {initial_users_count} 个用户")

    def get_status(self):
        """获取系统状态"""
        return self.handle.get_status()


def main():
    """主函数"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    federation = DynamicFederation()

    try:
        federation.start_federation()

        while federation.is_training:
            status = federation.get_status()
            logger.info(f"系统状态: 轮次{status['current_epoch']}, "
                        f"活跃用户{status['active_users']}, "
                        f"可用用户池{status['available_users']}, "
                        f"训练{'暂停' if federation.training_paused else '进行中'}")
            time.sleep(30)

    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止系统...")
    finally:
        federation.stop_federation()
        logger.info("系统已完全停止")


if __name__ == "__main__":
    main()