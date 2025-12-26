// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./HyperCoin.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract FederationManager is Ownable {
    HyperCoin public token;

    struct Task {
        string taskId;
        address creator;
        string modelHash;
        uint256 rewardPool;
        bool isCompleted;
        address[] participants;
    }

    // 这里需要映射存储每个参与者的比例
    mapping(string => mapping(address => uint256)) public taskShareRatios;
    mapping(string => Task) public tasks;

    // 这里的 Ownable(msg.sender) 是修复关键
    constructor(address _tokenAddress) Ownable(msg.sender) {
        token = HyperCoin(_tokenAddress);
    }

    function createTask(string memory _taskId, uint256 _rewardPool) public {
        Task storage newTask = tasks[_taskId];
        newTask.taskId = _taskId;
        newTask.creator = msg.sender;
        newTask.rewardPool = _rewardPool;
        newTask.isCompleted = false;
    }

    function setContributionRatios(
        string memory _taskId, 
        address[] memory _users, 
        uint256[] memory _ratios,
        string memory _modelHash
    ) public onlyOwner {
        Task storage task = tasks[_taskId];
        task.modelHash = _modelHash;
        
        delete task.participants;
        for (uint i = 0; i < _users.length; i++) {
            taskShareRatios[_taskId][_users[i]] = _ratios[i];
            // 将用户加入参与者列表以便后续分红
            task.participants.push(_users[i]);
        }
        task.isCompleted = true;
    }

    // 后续每次使用模型分发收益
    function distributeRevenue(string memory _taskId, uint256 _amount) public {
        Task storage task = tasks[_taskId];
        require(task.isCompleted, "Task not completed");

        for (uint i = 0; i < task.participants.length; i++) {
            address user = task.participants[i];
            uint256 userShare = (_amount * taskShareRatios[_taskId][user]) / 10000;
            if (userShare > 0) {
                token.transferFrom(msg.sender, user, userShare);
            }
        }
    }
}