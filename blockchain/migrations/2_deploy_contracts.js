const HyperCoin = artifacts.require("HyperCoin");
const FederationManager = artifacts.require("FederationManager");

module.exports = async function (deployer) {
  await deployer.deploy(HyperCoin);
  const token = await HyperCoin.deployed();
  await deployer.deploy(FederationManager, token.address);
};