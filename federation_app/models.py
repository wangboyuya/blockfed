from django.db import models
from django.contrib.auth.models import AbstractUser
import json

class User(AbstractUser):
    """扩展Django内置用户模型"""
    ganache_index = models.IntegerField(
        unique=True,
        null=True,
        blank=True,
        verbose_name="Ganache账户索引",
        help_text="对应Ganache中的账户索引(0-9)"
    )
    # 以下字段已废弃，保留仅用于数据迁移兼容
    # 实际余额请使用 user.eth_balance（从Ganache实时读取）
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="账户余额(已废弃)")
    virtual_coins = models.IntegerField(default=0, verbose_name="虚拟币(已废弃)")

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.username

    @property
    def wallet_address(self):
        """获取用户对应的Ganache钱包地址"""
        if self.ganache_index is None:
            return None
        try:
            from federation_app.blockchain_utils import w3
            return w3.eth.accounts[self.ganache_index]
        except Exception as e:
            print(f"获取钱包地址失败: {e}")
            return None

    @property
    def eth_balance(self):
        """从Ganache读取实时ETH余额（推荐使用）"""
        if not self.wallet_address:
            return 0.0
        try:
            from federation_app.blockchain_utils import w3
            balance_wei = w3.eth.get_balance(self.wallet_address)
            balance_eth = w3.from_wei(balance_wei, 'ether')
            return float(balance_eth)
        except Exception as e:
            print(f"获取ETH余额失败: {e}")
            return 0.0

class FederationTask(models.Model):
    TASK_STATUS = [
        ('running', '运行中'),
        ('paused', '已暂停'),
        ('stopped', '已停止'),
        ('completed', '已完成'),
    ]

    MODEL_CHOICES = [
        ('CNN', 'CNN'),
        ('r8', 'ResNet8'),
        ('r18', 'ResNet18'),
        ('r34', 'ResNet34'),
    ]

    DATASET_CHOICES = [
        ('MNIST', 'MNIST'),
        ('CIFAR10', 'CIFAR10'),
    ]

    PAYMENT_MODES = [
        ('reward', '奖金池模式'),
        ('shareholding', '股份制模式'),
    ]

    MODEL_STATUS = [
        ('training', '训练中'),
        ('online', '已上线'),
        ('offline', '已下线'),
    ]

    task_id = models.CharField(max_length=50, unique=True, verbose_name="任务编号")
    task_name = models.CharField(max_length=100, verbose_name="任务名称")
    description = models.TextField(blank=True, verbose_name="任务描述")
    status = models.CharField(max_length=20, choices=TASK_STATUS, default='running', verbose_name="任务状态")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")
    current_epoch = models.IntegerField(default=0, verbose_name="当前轮次")
    total_epochs = models.IntegerField(default=100, verbose_name="总轮次")
    active_users = models.IntegerField(default=0, verbose_name="活跃用户数")

    model_architecture = models.CharField(max_length=20, choices=MODEL_CHOICES, default='r8', verbose_name="模型结构")
    dataset = models.CharField(max_length=20, choices=DATASET_CHOICES, default='CIFAR10', verbose_name="数据集")
    epochs = models.IntegerField(default=2000, verbose_name="训练轮数")
    reward_pool = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="奖金池")

    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODES, default='shareholding', verbose_name="支付模式")
    model_status = models.CharField(max_length=20, choices=MODEL_STATUS, default='training', verbose_name="模型状态")
    usage_fee_per_request = models.DecimalField(max_digits=10, decimal_places=2, default=0.50, verbose_name="单次使用费")
    total_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="累计收益")
    total_usage_count = models.IntegerField(default=0, verbose_name="累计使用次数")
    creator = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_tasks', verbose_name="创建者")

    class Meta:
        verbose_name = "联邦学习任务"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.task_name} ({self.task_id})"
    

class TaskParticipant(models.Model):
    task = models.ForeignKey(FederationTask, on_delete=models.CASCADE, related_name='participants', verbose_name="联邦任务")
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="用户")
    joined_at = models.DateTimeField(auto_now_add=True, verbose_name="加入时间")
    is_active = models.BooleanField(default=True, verbose_name="是否活跃")

    class Meta:
        verbose_name = "任务参与者"
        verbose_name_plural = verbose_name
        unique_together = ['task', 'user']

    def __str__(self):
        return f"{self.user.username} - {self.task.task_name}"

class TaskLog(models.Model):
    LOG_LEVELS = [
        ('info', '信息'),
        ('warning', '警告'),
        ('error', '错误'),
        ('success', '成功'),
    ]
    
    task = models.ForeignKey(FederationTask, on_delete=models.CASCADE, related_name='logs', verbose_name="任务")
    level = models.CharField(max_length=10, choices=LOG_LEVELS, default='info', verbose_name="日志级别")
    message = models.TextField(verbose_name="日志内容")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="记录时间")
    
    class Meta:
        verbose_name = "任务日志"
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.task.task_id} - {self.level} - {self.message[:50]}"
    

class GlobalAccuracy(models.Model):
    """全局准确度记录"""
    task = models.ForeignKey(FederationTask, on_delete=models.CASCADE, related_name='global_accuracies', verbose_name="联邦任务")
    epoch = models.IntegerField(verbose_name="训练轮次")
    accuracy = models.FloatField(verbose_name="全局准确度")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="记录时间")
    
    class Meta:
        verbose_name = "全局准确度记录"
        verbose_name_plural = verbose_name
        ordering = ['epoch']
        unique_together = ['task', 'epoch']
    
    def __str__(self):
        return f"{self.task.task_id} - 轮次{self.epoch}: {self.accuracy:.2f}%"


class UserAsset(models.Model):
    """用户资产表"""
    ASSET_TYPES = [
        ('data', '数据块'),
        ('model_share', '模型股份'),
        ('virtual_coin', '虚拟币'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assets', verbose_name="用户")
    asset_type = models.CharField(max_length=20, choices=ASSET_TYPES, verbose_name="资产类型")
    asset_reference = models.CharField(max_length=100, verbose_name="资产引用ID")
    quantity = models.DecimalField(max_digits=10, decimal_places=4, verbose_name="数量")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "用户资产"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.user.username} - {self.asset_type}: {self.quantity}"


class Transaction(models.Model):
    """交易记录表"""
    TRANSACTION_TYPES = [
        ('recharge', '充值'),
        ('withdraw', '提现'),
        ('model_usage', '模型使用'),
        ('revenue', '收益分配'),
        ('share_trade', '股份交易'),
        ('data_purchase', '数据购买'),
        ('reward_distribution', '奖金分配'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions', verbose_name="用户")
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES, verbose_name="交易类型")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="交易金额")
    balance_before = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="交易前余额")
    balance_after = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="交易后余额")
    description = models.TextField(verbose_name="交易描述")
    related_task = models.ForeignKey(FederationTask, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="关联任务")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "交易记录"
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.transaction_type}: ¥{self.amount}"


class ModelShareholding(models.Model):
    """模型股份持有记录"""
    task = models.ForeignKey(FederationTask, on_delete=models.CASCADE, related_name='shareholdings', verbose_name="联邦任务")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shareholdings', verbose_name="用户")
    share_ratio = models.DecimalField(max_digits=10, decimal_places=6, verbose_name="股份占比")
    initial_contribution = models.DecimalField(max_digits=10, decimal_places=6, verbose_name="初始贡献度")
    tradable = models.BooleanField(default=True, verbose_name="是否可交易")
    acquired_at = models.DateTimeField(auto_now_add=True, verbose_name="获得时间")

    class Meta:
        verbose_name = "模型股份持有记录"
        verbose_name_plural = verbose_name
        unique_together = ['task', 'user']

    def __str__(self):
        return f"{self.user.username} - {self.task.task_name}: {self.share_ratio*100:.2f}%"


class ModelUsageRecord(models.Model):
    """模型使用记录"""
    task = models.ForeignKey(FederationTask, on_delete=models.CASCADE, related_name='usage_records', verbose_name="联邦任务")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='model_usages', verbose_name="使用者")
    usage_fee = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="使用费用")
    usage_type = models.CharField(max_length=20, default='prediction', verbose_name="使用类型")
    input_data_hash = models.CharField(max_length=64, blank=True, verbose_name="输入数据哈希")
    prediction_result = models.TextField(blank=True, verbose_name="预测结果")
    used_at = models.DateTimeField(auto_now_add=True, verbose_name="使用时间")

    class Meta:
        verbose_name = "模型使用记录"
        verbose_name_plural = verbose_name
        ordering = ['-used_at']

    def __str__(self):
        return f"{self.user.username}使用{self.task.task_name} - ¥{self.usage_fee}"


class RevenueDistribution(models.Model):
    """收益分配记录"""
    task = models.ForeignKey(FederationTask, on_delete=models.CASCADE, related_name='revenue_distributions', verbose_name="联邦任务")
    shareholder = models.ForeignKey(User, on_delete=models.CASCADE, related_name='revenues', verbose_name="股东")
    revenue_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="收益金额")
    source_usage = models.ForeignKey(ModelUsageRecord, on_delete=models.CASCADE, verbose_name="来源使用记录")
    share_ratio_snapshot = models.DecimalField(max_digits=10, decimal_places=6, verbose_name="股份占比快照")
    distributed_at = models.DateTimeField(auto_now_add=True, verbose_name="分配时间")

    class Meta:
        verbose_name = "收益分配记录"
        verbose_name_plural = verbose_name
        ordering = ['-distributed_at']

    def __str__(self):
        return f"{self.shareholder.username}从{self.task.task_name}获得¥{self.revenue_amount}"


class RewardDistribution(models.Model):
    """奖金分配记录（奖金池模式）"""
    task = models.ForeignKey(FederationTask, on_delete=models.CASCADE, related_name='reward_distributions', verbose_name="联邦任务")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rewards', verbose_name="用户")
    contribution_ratio = models.DecimalField(max_digits=10, decimal_places=6, verbose_name="贡献占比")
    reward_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="奖金金额")
    paid = models.BooleanField(default=False, verbose_name="是否已支付")
    distributed_at = models.DateTimeField(auto_now_add=True, verbose_name="分配时间")

    class Meta:
        verbose_name = "奖金分配记录"
        verbose_name_plural = verbose_name
        unique_together = ['task', 'user']

    def __str__(self):
        return f"{self.user.username}从{self.task.task_name}获得奖金¥{self.reward_amount}"


class DataBlock(models.Model):
    """数据块模型 - 存储所有数据块信息"""
    DATASET_TYPES = [
        ('CIFAR10', 'CIFAR-10'),
        ('MNIST', 'MNIST'),
    ]

    block_id = models.IntegerField(unique=True, primary_key=True, verbose_name="数据块ID")
    dataset_type = models.CharField(max_length=20, choices=DATASET_TYPES, default='CIFAR10', verbose_name="数据集类型")
    data_size = models.IntegerField(default=0, verbose_name="数据样本数量")
    base_price = models.IntegerField(default=10, verbose_name="基础价格(虚拟币)")
    is_available = models.BooleanField(default=True, verbose_name="是否可购买")
    current_owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_blocks', verbose_name="当前拥有者")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "数据块"
        verbose_name_plural = verbose_name
        ordering = ['block_id']

    def __str__(self):
        owner_name = self.current_owner.username if self.current_owner else "无"
        return f"数据块 #{self.block_id} - 拥有者: {owner_name}"


class UserDataBlock(models.Model):
    """用户数据块持有记录"""
    ACQUISITION_TYPES = [
        ('free', '免费赠送'),
        ('purchased', '购买获得'),
        ('rewarded', '奖励获得'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='data_blocks', verbose_name="用户")
    data_block = models.ForeignKey(DataBlock, on_delete=models.CASCADE, related_name='ownership_records', verbose_name="数据块")
    acquisition_type = models.CharField(max_length=20, choices=ACQUISITION_TYPES, default='purchased', verbose_name="获得方式")
    acquired_at = models.DateTimeField(auto_now_add=True, verbose_name="获得时间")

    class Meta:
        verbose_name = "用户数据块持有记录"
        verbose_name_plural = verbose_name
        unique_together = ['user', 'data_block']  # 独占模式：同一数据块只能被一个用户持有
        ordering = ['-acquired_at']

    def __str__(self):
        return f"{self.user.username} 持有数据块 #{self.data_block.block_id}"


class DataBlockTransaction(models.Model):
    """数据块交易记录"""
    TRANSACTION_TYPES = [
        ('purchase', '购买'),
        ('sell', '出售'),
        ('gift', '赠送'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='datablock_transactions', verbose_name="用户")
    data_block = models.ForeignKey(DataBlock, on_delete=models.CASCADE, related_name='transactions', verbose_name="数据块")
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES, verbose_name="交易类型")
    price = models.IntegerField(verbose_name="交易价格(虚拟币)")
    coins_before = models.IntegerField(verbose_name="交易前虚拟币")
    coins_after = models.IntegerField(verbose_name="交易后虚拟币")
    description = models.TextField(blank=True, verbose_name="交易描述")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="交易时间")

    class Meta:
        verbose_name = "数据块交易记录"
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.get_transaction_type_display()}数据块 #{self.data_block.block_id} - {self.price}币"
