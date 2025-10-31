# contribution_manager.py
import os
import json
import random
import logging
import numpy as np
from datetime import datetime


class ContributionManager:
    def __init__(self, task_id, saved_models_dir, max_users_per_round=5):
        self.task_id = task_id
        self.contribution_file = os.path.join(saved_models_dir, 'contribution_records.json')
        self.max_users = max_users_per_round
        self.logger = logging.getLogger(f"task_{task_id}")

        # 初始化记录文件
        self._init_contribution_file()

    def _init_contribution_file(self):
        """初始化贡献度记录文件"""
        if not os.path.exists(self.contribution_file):
            records = {
                "task_id": self.task_id,
                "created_time": datetime.now().isoformat(),
                "round_records": {},
                "user_total_contributions": {}
            }
            self._save_records(records)

    def _load_records(self):
        """加载贡献度记录"""
        try:
            with open(self.contribution_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "task_id": self.task_id,
                "created_time": datetime.now().isoformat(),
                "round_records": {},
                "user_total_contributions": {}
            }

    def _save_records(self, records):
        """保存贡献度记录"""
        os.makedirs(os.path.dirname(self.contribution_file), exist_ok=True)
        with open(self.contribution_file, 'w') as f:
            json.dump(records, f, indent=2)

    def select_users_for_evaluation(self, available_users):
        """选择本轮参与贡献度评估的用户（最多5个）"""
        if len(available_users) <= self.max_users:
            return available_users
        else:
            return random.sample(available_users, self.max_users)

    def record_round_contribution(self, round_num, user_contributions):
        """记录单轮贡献度"""
        records = self._load_records()

        # 记录本轮贡献
        round_key = f"round_{round_num}"
        records["round_records"][round_key] = {
            "timestamp": datetime.now().isoformat(),
            "contributions": user_contributions
        }

        # 更新用户累计贡献
        for user_id, contribution in user_contributions.items():
            user_key = str(user_id)
            if user_key in records["user_total_contributions"]:
                records["user_total_contributions"][user_key] += contribution
            else:
                records["user_total_contributions"][user_key] = contribution

        self._save_records(records)
        self.logger.info(f"第 {round_num} 轮贡献度记录已保存")

    def get_user_final_ratios(self):
        """获取用户最终收益分配比例"""
        records = self._load_records()
        total_contributions = records["user_total_contributions"]

        if not total_contributions:
            return {}

        total_sum = sum(total_contributions.values())
        if total_sum == 0:
            # 如果总贡献为0，则平均分配
            user_count = len(total_contributions)
            return {user_id: 1.0 / user_count for user_id in total_contributions.keys()}

        return {user_id: contrib / total_sum for user_id, contrib in total_contributions.items()}