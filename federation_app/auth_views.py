"""
用户认证相关视图
"""
import json
from decimal import Decimal
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction
from .models import User, Transaction
from .datablock_service import datablock_market_service
from .blockchain_utils import sync_contribution_to_chain, get_contract

@csrf_exempt
@require_http_methods(["POST"])
@transaction.atomic
def register_user(request):
    """用户注册 - 自动分配100虚拟币和3个免费数据块"""
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        email = data.get('email', '')

        if not username or not password:
            return JsonResponse({'success': False, 'error': '用户名和密码不能为空'})

        if User.objects.filter(username=username).exists():
            return JsonResponse({'success': False, 'error': '用户名已存在'})

        # 创建用户（初始100虚拟币）
        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
            balance=Decimal('0.00'),
            virtual_coins=100  # 注册赠送100虚拟币
        )

        # 分配3个免费数据块
        allocation_result = datablock_market_service.allocate_free_blocks(user, num_blocks=3)

        if not allocation_result['success']:
            # 如果分配失败，记录警告但不影响注册
            print(f"警告：用户 {username} 注册成功，但数据块分配失败: {allocation_result['message']}")
            allocated_blocks = []
        else:
            allocated_blocks = allocation_result.get('block_ids', [])

        # 登录用户
        login(request, user)

        return JsonResponse({
            'success': True,
            'message': '注册成功',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'balance': float(user.balance),
                'virtual_coins': user.virtual_coins,
                'allocated_blocks': allocated_blocks,
                'allocated_blocks_count': len(allocated_blocks)
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def login_user(request):
    """用户登录"""
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return JsonResponse({'success': False, 'error': '用户名和密码不能为空'})

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return JsonResponse({
                'success': True,
                'message': '登录成功',
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'balance': float(user.balance),
                    'virtual_coins': user.virtual_coins
                }
            })
        else:
            return JsonResponse({'success': False, 'error': '用户名或密码错误'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def logout_user(request):
    """用户登出"""
    try:
        logout(request)
        return JsonResponse({'success': True, 'message': '登出成功'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def get_user_profile(request):
    """获取用户信息"""
    try:
        user = request.user
        return JsonResponse({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'balance': float(user.balance),
                'virtual_coins': user.virtual_coins,
                'date_joined': user.date_joined.strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def get_user_transactions(request):
    """获取用户交易记录"""
    try:
        user = request.user
        transactions = Transaction.objects.filter(user=user).order_by('-created_at')[:50]

        transactions_data = [{
            'id': t.id,
            'type': t.transaction_type,
            'type_display': t.get_transaction_type_display(),
            'amount': float(t.amount),
            'balance_before': float(t.balance_before),
            'balance_after': float(t.balance_after),
            'description': t.description,
            'created_at': t.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'related_task_id': t.related_task.task_id if t.related_task else None
        } for t in transactions]

        return JsonResponse({
            'success': True,
            'transactions': transactions_data
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
@transaction.atomic
def recharge_balance(request):
    """充值余额（模拟）"""
    try:
        data = json.loads(request.body)
        amount = Decimal(str(data.get('amount', 0)))

        if amount <= 0:
            return JsonResponse({'success': False, 'error': '充值金额必须大于0'})

        user = request.user
        balance_before = user.balance
        user.balance += amount
        user.save()

        Transaction.objects.create(
            user=user,
            transaction_type='recharge',
            amount=amount,
            balance_before=balance_before,
            balance_after=user.balance,
            description=f'充值¥{amount}'
        )
        hc_contract = get_contract('HyperCoin')
        admin = w3.eth.accounts[0]
        user_address = w3.eth.accounts[request.user.id % 10]
        hc_contract.functions.faucet(user_address, 100 * 10**18).transact({'from': admin})

        return JsonResponse({
            'success': True,
            'message': '充值成功',
            'balance': float(user.balance)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
@transaction.atomic
def purchase_virtual_coins(request):
    """使用账户余额购买虚拟币"""
    try:
        data = json.loads(request.body)
        coin_amount = int(data.get('amount', 0))

        if coin_amount <= 0:
            return JsonResponse({'success': False, 'error': '购买数量必须大于0'})

        # 汇率：1元 = 10虚拟币
        exchange_rate = 10
        cost = Decimal(str(coin_amount / exchange_rate))

        user = request.user

        if user.balance < cost:
            return JsonResponse({
                'success': False,
                'error': f'余额不足，需要¥{cost:.2f}，当前余额¥{user.balance:.2f}'
            })

        # 扣除余额
        balance_before = user.balance
        user.balance -= cost
        user.virtual_coins += coin_amount
        user.save()

        # 记录交易
        Transaction.objects.create(
            user=user,
            transaction_type='purchase',
            amount=-cost,
            balance_before=balance_before,
            balance_after=user.balance,
            description=f'购买{coin_amount}虚拟币'
        )

        return JsonResponse({
            'success': True,
            'message': f'成功购买{coin_amount}虚拟币',
            'balance': float(user.balance),
            'virtual_coins': user.virtual_coins
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
@transaction.atomic
def purchase_data_blocks(request):
    """使用虚拟币购买数据块"""
    try:
        data = json.loads(request.body)
        data_block_ids = data.get('data_block_ids', [])
        cost_per_block = 10

        if not data_block_ids:
            return JsonResponse({'success': False, 'error': '请选择要购买的数据块'})

        user = request.user
        total_cost = len(data_block_ids) * cost_per_block

        if user.virtual_coins < total_cost:
            return JsonResponse({
                'success': False,
                'error': f'虚拟币不足，需要{total_cost}虚拟币，当前仅有{user.virtual_coins}虚拟币'
            })

        user.virtual_coins -= total_cost
        user.save()

        return JsonResponse({
            'success': True,
            'message': f'成功购买{len(data_block_ids)}个数据块',
            'virtual_coins': user.virtual_coins,
            'purchased_blocks': data_block_ids
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
def check_auth_status(request):
    """检查用户登录状态"""
    if request.user.is_authenticated:
        return JsonResponse({
            'authenticated': True,
            'user': {
                'id': request.user.id,
                'username': request.user.username,
                'balance': float(request.user.balance),
                'virtual_coins': request.user.virtual_coins
            }
        })
    else:
        return JsonResponse({'authenticated': False})
