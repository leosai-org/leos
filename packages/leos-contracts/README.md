# leos-contracts

`leos-contracts` is the runtime validator for governed LEOS JSON contracts.
It does not define or embed schemas.

The contract root is resolved deterministically:

1. `LEOS_CONTRACT_ROOT`, when set; otherwise
2. the repository's canonical `contracts/` directory only when the package
   positively identifies the expected LEOS source-checkout structure.

Containers must set `LEOS_CONTRACT_ROOT` to the copied canonical contract
artifacts (the promoted v2 services use `/opt/leos/contracts`).

An installed package outside that verified source layout must set
`LEOS_CONTRACT_ROOT`; it never falls back to a nearby environment or virtual
environment `contracts/` directory. Missing, incomplete, or malformed
governed roots raise `ContractRootError`.
