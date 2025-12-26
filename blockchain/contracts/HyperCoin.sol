// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract HyperCoin is ERC20, Ownable {
    // 这里的 Ownable(msg.sender) 是修复关键
    constructor() ERC20("HyperCoin", "HC") Ownable(msg.sender) {
        _mint(msg.sender, 1000000 * 10**decimals()); 
    }

    function faucet(address to, uint256 amount) public onlyOwner {
        _transfer(owner(), to, amount);
    }
}