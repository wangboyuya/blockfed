from django.urls import path
from . import views, auth_views, asset_views, datablock_views

urlpatterns = [
    # 主页面路由
    path('', views.index_redirect, name='index'),  # 根路径重定向到dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    path('predict/', views.prediction_page, name='prediction_page'),
    path('profile/', views.profile_page, name='profile_page'),
    path('login/', views.login_page, name='login_page'),

    # 用户认证API
    path('api/auth/register/', auth_views.register_user, name='register_user'),
    path('api/auth/login/', auth_views.login_user, name='login_user'),
    path('api/auth/logout/', auth_views.logout_user, name='logout_user'),
    path('api/auth/status/', auth_views.check_auth_status, name='check_auth_status'),
    path('api/auth/profile/', auth_views.get_user_profile, name='get_user_profile'),
    path('api/auth/transactions/', auth_views.get_user_transactions, name='get_user_transactions'),
    path('api/auth/recharge/', auth_views.recharge_balance, name='recharge_balance'),
    path('api/auth/purchase-coins/', auth_views.purchase_virtual_coins, name='purchase_virtual_coins'),
    path('api/auth/purchase-data/', auth_views.purchase_data_blocks, name='purchase_data_blocks'),

    # 用户资产API
    path('api/user/assets/', asset_views.get_user_assets, name='get_user_assets'),
    path('api/user/shareholdings/', asset_views.get_user_shareholdings, name='get_user_shareholdings'),
    path('api/user/participations/', asset_views.get_user_participations, name='get_user_participations'),
    path('api/user/revenues/', asset_views.get_user_revenues, name='get_user_revenues'),
    path('api/user/data-blocks/', asset_views.get_user_data_blocks, name='get_user_data_blocks'),

    # 数据块市场API
    path('api/datablock/market/', datablock_views.get_datablock_market, name='get_datablock_market'),
    path('api/datablock/my-blocks/', datablock_views.get_my_datablocks, name='get_my_datablocks'),
    path('api/datablock/purchase/', datablock_views.purchase_datablock, name='purchase_datablock'),
    path('api/datablock/sell/', datablock_views.sell_datablock, name='sell_datablock'),
    path('api/datablock/transactions/', datablock_views.get_datablock_transactions, name='get_datablock_transactions'),
    path('api/datablock/stats/', datablock_views.get_datablock_stats, name='get_datablock_stats'),
    path('api/datablock/initialize/', datablock_views.initialize_datablocks, name='initialize_datablocks'),

    # 任务管理API
    path('api/tasks/create/', views.create_task, name='create_task'),
    path('api/tasks/join/', views.join_task, name='join_task'),
    path('api/tasks/leave/', views.leave_task, name='leave_task'),
    path('api/tasks/delete/', views.delete_task, name='delete_task'),
    path('api/tasks/restart/', views.restart_task, name='restart_task'),
    path('api/tasks/clear-logs/', views.clear_logs, name='clear_logs'),
    path('api/tasks/status/', views.get_all_status, name='get_all_status'),
    path('api/tasks/<str:task_id>/status/', views.get_task_status, name='get_task_status'),
    path('api/tasks/accuracy-history/', views.get_accuracy_history, name='get_accuracy_history'),
    path('api/tasks/logs/', views.get_logs, name='get_logs'),

    # 模型预测相关路由
    path('api/predict/', views.predict_image, name='predict_image'),
    path('api/models/available/', views.get_available_models, name='get_available_models'),
    path('api/models/<str:task_id>/info/', views.get_model_info, name='get_model_info'),
]