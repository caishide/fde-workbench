# 导入轮第一批清单与指纹（L 线 round2：卡24 127 例＋文集 B 演练 7 件，2026-11-12；勘误 v2 见 §5）

> **性质**：登记表（ks1 线挂账消解——训练场挂账与卡24 127 例导入排期销号件）。上游：batch-2 拍板②（卡24 127 例排进 L 线导入排期）、PROGRESS「训练场与育才挂账」节。
> **纪律**：导入卡与导入包（含判卷基准）**全部只存本地真相层**（`D:\test\FDE\knowledge\交付场景导入包\round2\`，与 L1 首批的 `cards\packages` 目录隔离），本表只登记指针＋sha256＋许可快照——仓库被扫面零判卷材料。
> **转换器**：`scripts/simulation/import_cases.py` 四闸（卡 schema 允许名单 → `validate_scenario` 八规则 → `load_view` 三视图泄漏自检 → 输出目录仓内拒绝）。终版四闸实测：工作流终闸（01:09）127/127＋主会话复核（01:11）134 包／失败 0——两轮独立执行结论一致。
> **起草来源**：127 例＝卡24 案例库（MIT，见 §3）条目独立改编，全部由起草工作流产出。其中 42 例为写手复跑终稿（覆盖初版登记时点版本——初版中 33 例为主会话按同一提示词契约补齐的过渡态，见 §5 事件记录）；红线全程一致：企业名一律代号化、源效果数字零写入、全中文、判卷基准为方法论判据。文集 B 演练 7 件＝无开源许可文集 B 实战演练篇**仅思想层**原创重写（零条目清单/分级表/分钟级模板/阈值组合复现）。

## §1 导入包清单（status='draft'，待人工审阅后建行/激活）

### 1a. 卡24 127 例（MIT 案例库改编，家族 IMP-<CASE-ID>）

| scenario_key | 名称 | 来源指针 | 许可 | 快照 | 包 sha256 | 卡 sha256 |
|---|---|---|---|---|---|---|
| `IMP-AWS-ALTISOURCE-001` |  | 真相层 FDE-case-library/data/cases.json#aws-altisource- | MIT（FDE-case-library） | 2026-11-12 | `d7d84b965947619d8f2ee068e47514a1523fccc96cefe1161faab3842c110041` | `2b6995f943ab857f471867d51cda219a11939fbfe1f25d52f6fa3d6a9f0e166e` |
| `IMP-AWS-JABIL-001` |  | 真相层 FDE-case-library/data/cases.json#aws-jabil-001（c | MIT（FDE-case-library） | 2026-11-12 | `0780a982d1c4783e69dfba6feb8add132a045a28523b8a8e4ce2f0b4f5d1d1cf` | `09d1688099f6105f10bdc98f1aa24b7288f0025a3e154eae5b8aed543305f94b` |
| `IMP-DATAWHALE-001` |  | 真相层 FDE-case-library/data/cases.json#datawhale-001（c | MIT（FDE-case-library） | 2026-11-12 | `b2d54c1f10ad8af8ac6b5214eeea449afa720a90045fa72a23e525dd1b1005ce` | `32776353ddff32cb9033f15fc661403596440c5bfef9185361d74469da6d627d` |
| `IMP-DATAWHALE-002` |  | 真相层 FDE-case-library/data/cases.json#datawhale-002（c | MIT（FDE-case-library） | 2026-11-12 | `5dc5863008e559642c9cdf7c74a63bf4222eee29f671cd09883016bcd15e09d2` | `999ffd989a8a972e3d94f37d3169cc3e7410bfb7aec02e1ecdcbddf4318c8214` |
| `IMP-DATAWHALE-003` |  | 真相层 FDE-case-library/data/cases.json#datawhale-003（c | MIT（FDE-case-library） | 2026-11-12 | `289d3a88b8a12897ece28bb445445d0bec367dbacf4913193d0088d5e20b4d24` | `876bf809de51187ac4c4302d6cb662386fe69939bf4745158768ac410dbd15ae` |
| `IMP-DATAWHALE-004` |  | 真相层 FDE-case-library/data/cases.json#datawhale-004（c | MIT（FDE-case-library） | 2026-11-12 | `3969a92fdf2c9ac80f11687fa00a7fc21596b0e83c7cf4ad71ce2a5b8ed3729e` | `3c77874d6d039be2ab0a4b21e6c409a14a167ee0adc685f6274664e29aeee0de` |
| `IMP-DATAWHALE-005` |  | 真相层 FDE-case-library/data/cases.json#datawhale-005（c | MIT（FDE-case-library） | 2026-11-12 | `59e1d59edecdf7657a07c23197c89673b12933e2fb612cf7dfab1382cc7630f7` | `8158455a272273fd14df5da5073b8fcccd15af756700b67101b3dea4c28cf0d7` |
| `IMP-DATAWHALE-006` |  | 真相层 FDE-case-library/data/cases.json#datawhale-006（c | MIT（FDE-case-library） | 2026-11-12 | `668ff836d388cecb4f9b24b305fce263910297c7b0bdc504ead355849519150f` | `d31f0225cc2daa6537b6d4939f0c79c5702974d75bd2b305184c9be1e7ea8be9` |
| `IMP-DATAWHALE-007` |  | 真相层 FDE-case-library/data/cases.json#datawhale-007（c | MIT（FDE-case-library） | 2026-11-12 | `793dd8aa8d2bf968c6c91b8107f3e8b7596bc17854f81cd7db26f53ea36822cf` | `d826a8bab2c0c7db5d408dfe2d2ea661ff1db3fc82439b6866490f2d861982ca` |
| `IMP-DATAWHALE-008` |  | 真相层 FDE-case-library/data/cases.json#datawhale-008（c | MIT（FDE-case-library） | 2026-11-12 | `9419b084dba6999d6a3d4ba53fb9e77e3d6f3c807e8a3a8d76f4657ca5f842e5` | `53e10a4499c53979588570d4ce35f448c6ead525e1e04077c9cc8ceec0151d90` |
| `IMP-DATAWHALE-009` |  | 真相层 FDE-case-library/data/cases.json#datawhale-009（c | MIT（FDE-case-library） | 2026-11-12 | `0256cf4bb057bf6f4ca37b0c5595ceeae9678e5886bf363aa750a318ac60dd3a` | `32a085d16e2f9fa2e41b318a3397c5414309d1d70147069957c5832db10057f2` |
| `IMP-DATAWHALE-010` |  | 真相层 FDE-case-library/data/cases.json#datawhale-010（c | MIT（FDE-case-library） | 2026-11-12 | `53d98077b023274d0152acf349a2a9bce0407581f7f9536477d31deb2c3b8dd6` | `a47427ce98590af28b95c91ad62d4dd377b2ed11ef4c04d146ee12a24221ba58` |
| `IMP-DATAWHALE-011` |  | 真相层 FDE-case-library/data/cases.json#datawhale-011（c | MIT（FDE-case-library） | 2026-11-12 | `bfd3e1ddb4b32322bb5ec83d29e1e733693f395f11fe9b9ba7a5d0cb7b25ae5e` | `d5e71f01aacdcfde4b074fabd135a3a5380faf99b6959aa342c687938d06bbe9` |
| `IMP-DATAWHALE-012` |  | 真相层 FDE-case-library/data/cases.json#datawhale-012（c | MIT（FDE-case-library） | 2026-11-12 | `430eea43ca27ae1c4efc56a12d41c528baf591cb6616881fd8bb7a3ab83d200c` | `8611443b4d61880168a90a13969ad2ff5e6cebae15f37c72d5c8ce50d044c7e9` |
| `IMP-DATAWHALE-013` |  | 真相层 FDE-case-library/data/cases.json#datawhale-013（c | MIT（FDE-case-library） | 2026-11-12 | `fe79af0b0b3e8de3cdb87fafa53cf72d1d05a6f2ab91d91c6c5896d2487f8efd` | `71ac531f6287688860f1d65482fd5ef3071c11cc827fc70e1580e985193ca1d0` |
| `IMP-DATAWHALE-014` |  | 真相层 FDE-case-library/data/cases.json#datawhale-014（c | MIT（FDE-case-library） | 2026-11-12 | `8c102f5ba42c838f35ab1a071e8fed8f82fc20470f8831440bbfe103f291f5c4` | `5cbde226dd9de74d471991334a4a4911b36313e315cd8b9c8be9cc64cab7acce` |
| `IMP-DATAWHALE-015` |  | 真相层 FDE-case-library/data/cases.json#datawhale-015（c | MIT（FDE-case-library） | 2026-11-12 | `8efda8e604853fec6457ea53045f6b82cf0c266c4de22f3f327edc5ae7e2250f` | `b12620837ff1f633796ed1b4fa2828cb10713288d4c5fbcdbd75a129c40c209a` |
| `IMP-DATAWHALE-016` |  | 真相层 FDE-case-library/data/cases.json#datawhale-016（c | MIT（FDE-case-library） | 2026-11-12 | `b792cb90b13b7b5a081802936f835d8bd6f0a548260cc320b4f9ec0f277d716f` | `b739bd03ce7a568925f5a73e64d8dca6c5de8555e47d3392e6646aee21af550e` |
| `IMP-DATAWHALE-017` |  | 真相层 FDE-case-library/data/cases.json#datawhale-017（c | MIT（FDE-case-library） | 2026-11-12 | `f886185500733f17e9c25568e537b24f58ffb95ca273c4af2dd52a7cbd9c94e6` | `fb0365f487a1fdb198ba199e3cd90c2349fd14dd39b832d53c54d284d27d82ee` |
| `IMP-DATAWHALE-018` |  | 真相层 FDE-case-library/data/cases.json#datawhale-018（c | MIT（FDE-case-library） | 2026-11-12 | `75732dc78d8a1becd11df76ee06389411d0589b5597d16aa733babe7596d4f0e` | `54019f016de6e3b9ba261b0d124e5bcac8b6247b2e85e526c6e8066f4022bbd4` |
| `IMP-DATAWHALE-019` |  | 真相层 FDE-case-library/data/cases.json#datawhale-019（c | MIT（FDE-case-library） | 2026-11-12 | `261466ee2f5729258e5f9a23d43c1630afb7db268002f08607b433ff4dd92923` | `11163cbab8572c18740c403536f444be394f827638abb33e2a5f753bb7f290fb` |
| `IMP-DATAWHALE-020` |  | 真相层 FDE-case-library/data/cases.json#datawhale-020（c | MIT（FDE-case-library） | 2026-11-12 | `797828d1c87015876faf5b00352e41263deffb77777388684c3bc7520233f7c5` | `be6ea92f34c6ee992de5baecc1632668fe2b92bc1c12fb98f919537da7ae5f1d` |
| `IMP-DATAWHALE-021` |  | 真相层 FDE-case-library/data/cases.json#datawhale-021（c | MIT（FDE-case-library） | 2026-11-12 | `bfd62390d8d59a9b089364c9c53a0cbf220c7bc03e888390278837ec32e1437b` | `f9fa77376894a48fe42729e57dbfde5f4d88ddd2da103303ec0696370563b791` |
| `IMP-DATAWHALE-022` |  | 真相层 FDE-case-library/data/cases.json#datawhale-022（c | MIT（FDE-case-library） | 2026-11-12 | `9fbf6205aa399abb0ee3ec9eef22dd52267cbfaf64630a2817517e569b69dd5e` | `6ce35eaeceacc649e9aec31ad269d8ba85d128db55a441539987ec0818466b1c` |
| `IMP-DATAWHALE-023` |  | 真相层 FDE-case-library/data/cases.json#datawhale-023（c | MIT（FDE-case-library） | 2026-11-12 | `20f139301432fe8b4640ff1f99d3c3469e0c74a7378d7be1151326990067a8d3` | `be5f4c1150ff2b9d59a6edc065670bce353caaab59a73dd1081916ce613bf8a8` |
| `IMP-DATAWHALE-024` |  | 真相层 FDE-case-library/data/cases.json#datawhale-024（c | MIT（FDE-case-library） | 2026-11-12 | `b005f17a2e112c1a06589c61a807e3281112a6f0d93a0ce751355e7c03f390fb` | `98ee7e90c64a70f210ffa0ab5c92b73757c9cee6d32046fd3ec49a5f6dde611a` |
| `IMP-ENTERPRISE-BAYER-PRINCE-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-baye | MIT（FDE-case-library） | 2026-11-12 | `2c42f495ac37a73fd20d26928f7f36a16212476f43290743c989fb94678b5f15` | `ec2eb7dd030082368cc56918fb7fbf72b13a41a8f6834d6b1fbfe188b95e69fb` |
| `IMP-ENTERPRISE-BLOCK-GOOSE-G2-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-bloc | MIT（FDE-case-library） | 2026-11-12 | `ee53728bdc71ca6cf5a88357b9448de1db0f6c009af51d61c09214f4f62191e6` | `244a3251a026f29ed30c08d55205e4716cc3c4477c8d4f716cc90a1fdd1ab36d` |
| `IMP-ENTERPRISE-BMW-FACTORY-GENIUS-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-bmw- | MIT（FDE-case-library） | 2026-11-12 | `d7c14570d4aa1aa89f5e00238333a2b0b789fdcb37252dbec2f4b467c4821eba` | `56ec1675dca414fc10ea3a5b7fadc0d94992c92325bfd1c80ef9d6dcd703bf19` |
| `IMP-ENTERPRISE-BOSCH-VISUAL-INSPECTION-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-bosc | MIT（FDE-case-library） | 2026-11-12 | `a42a573ed4c146d4068e8488a465cc8aad7ad13c8b5473fd9800706ab2afcaea` | `5f47a6bf2a8f3371e6c666ae6e6421c26acbcfb63959584cebe223d093305713` |
| `IMP-ENTERPRISE-DBS-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-dbs- | MIT（FDE-case-library） | 2026-11-12 | `50d0093bf5e1b0da98f79c53d4e043415239edb9b8c9a3e28f1108042764ff08` | `b8e0d6ec82f25c702caf3664f56e9f6c21f11a3be54b36c4edd2d8ebd399b25d` |
| `IMP-ENTERPRISE-DOCTOLIB-AI-FACTORY-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-doct | MIT（FDE-case-library） | 2026-11-12 | `3f48c37f071dc251926178e6fb21ad28e2260925452b9fb78f3102e2a52bd1e1` | `9adc9d2a4ae189de769db6717972208ab24a1266d9102517bf5cd4d7173a604a` |
| `IMP-ENTERPRISE-DOORDASH-EVAL-FLYWHEEL-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-door | MIT（FDE-case-library） | 2026-11-12 | `2fc4bcd2582f3d5789e7c97ace83fb2eb6500e3ee3072b8f1d8bc5a7b189d247` | `56d35c352a05689e239dd8d502044571ecda4bf9d35646a03ea283e6e64dc7b2` |
| `IMP-ENTERPRISE-GRAB-LLM-KIT-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-grab | MIT（FDE-case-library） | 2026-11-12 | `20e8d8df1acd0615963bc37545178ef41ec2157261169acba2eb198980e68c22` | `91ccbe587da711e9a2fdd8d11f697f987d45734b89e2bf78ef78aa20bca5f084` |
| `IMP-ENTERPRISE-MCKINSEY-LILLI-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-mcki | MIT（FDE-case-library） | 2026-11-12 | `27700335c87193548f89369c4f13083c4147f7c71e56dd0ee2e2e5004f5162f3` | `5e032df6d5ecd6d676853b227025f5ac61c38c5c5c24cf5ad9daf0b39f51267e` |
| `IMP-ENTERPRISE-META-EXPERT-SECOND-BRAIN-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-meta | MIT（FDE-case-library） | 2026-11-12 | `7496c8741272ea2ae1074059064b60e9491ec9d95547d2c1f5874c89323600e1` | `b7bb4265465f56f4bff3a756c02fb54d544d9584aed33c96605a03f97f0a250d` |
| `IMP-ENTERPRISE-NUBANK-SUPPORT-AGENTS-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-nuba | MIT（FDE-case-library） | 2026-11-12 | `7c77759e32fc3c631dc3b61c464b975696ced62f32b718d67b1363e613769872` | `ee1e88378ca996ad2e01aeef2f31789c3354166f3e9e528276a53bc90f33a4d4` |
| `IMP-ENTERPRISE-TELSTRA-AI-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-tels | MIT（FDE-case-library） | 2026-11-12 | `ee289289728f23ddc4f5290f83a72855ab4cd0b60ea5f61b69ce2ef040fa199e` | `1c0f278b7af551152bd62efe7b201ebf1403399c3cbdb391893652258641c827` |
| `IMP-ENTERPRISE-UBER-GENIE-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-uber | MIT（FDE-case-library） | 2026-11-12 | `b600c68b2757ef19862b3ebfa0261a58469d27899a72bd84b41f63d0872e4312` | `078a36ab9d33b27ca7cc6afb4162672eb00cdbc2f62469173e1941e951850ded` |
| `IMP-ENTERPRISE-VODAFONE-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-voda | MIT（FDE-case-library） | 2026-11-12 | `4a222a648ab8551580668169c5f923aaf1af4c184d971913d359713514525a4b` | `4bafdd6e2ba3d7293aeb37e560d5004dabb2717eda0b6ddf621cd6d0be431d3d` |
| `IMP-ENTERPRISE-WALMART-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-walm | MIT（FDE-case-library） | 2026-11-12 | `7ea44dd36a2fc3939cca131a43063da94edd959f3558f412f03c15ec8f9d9ac9` | `d3e5366a7523ed93409851d1932767e27e26d6d128f05157be2c6f69d534fab9` |
| `IMP-GOOGLE-BERENBERG-001` |  | 真相层 FDE-case-library/data/cases.json#google-berenber | MIT（FDE-case-library） | 2026-11-12 | `9b4e11bb887b3bfecf1368c3908f44fab9f19bfe5d7a0d62962ff1a0ee984600` | `09d5f6e9680c19063ae66de1fc0a9a50f78e24c985cf78c24d9f1b71500ba067` |
| `IMP-IBM-LOCKHEED-MARTIN-001` |  | 真相层 FDE-case-library/data/cases.json#ibm-lockheed-ma | MIT（FDE-case-library） | 2026-11-12 | `0f401a186a741cc778241278fbe8c4908ad0ad63d7e116832fd9fadcf3d85a38` | `fd92cdebe931a8fde7e6947c3f9a7517ee410c944348421a28352f27b5e29ae8` |
| `IMP-IBM-MEDTRONIC-001` |  | 真相层 FDE-case-library/data/cases.json#ibm-medtronic-0 | MIT（FDE-case-library） | 2026-11-12 | `8c4fcceb87539cac3602d275472dabb55a1e4ed81276a6506da3d99502c29e3b` | `46fba0c20260ca8705a473d9221e7acdf314eaf854e2c99becc34320a753690c` |
| `IMP-MICROSOFT-PRESIDIO-001` |  | 真相层 FDE-case-library/data/cases.json#microsoft-presi | MIT（FDE-case-library） | 2026-11-12 | `ae9dcee7c81356930bcb456110d35045462076a355e4676fbd32bc1b4dd332cc` | `00c0b107d60c6f283743ab14053b1009a6b9a72adcabf4c0e84efc60dde308f6` |
| `IMP-MICROSOFT-ROLLS-ROYCE-001` |  | 真相层 FDE-case-library/data/cases.json#microsoft-rolls | MIT（FDE-case-library） | 2026-11-12 | `cb94fa40dc9431144818ac5ff004a06fb2286799f5c35c55e9ad9c0a6f648481` | `3032ff495360c7e0c9784fe20b0efa56ae1cb37e7ebd341b0b0a8358ae56cb4d` |
| `IMP-MICROSOFT-SYNEOS-HEALTH-001` |  | 真相层 FDE-case-library/data/cases.json#microsoft-syneo | MIT（FDE-case-library） | 2026-11-12 | `fba3c3ed2bc4524cb68e859e4f52a1945cc4140fbdb8f0fcc7676f48f5899338` | `37cdd2b4f746d54fdd14c9199fa70ac663cc09381c8a38a529029553463ee2ad` |
| `IMP-OPENAI-001` |  | 真相层 FDE-case-library/data/cases.json#openai-001（clon | MIT（FDE-case-library） | 2026-11-12 | `4f3e43a263e950a04e7924dc55e61bed713d7cbe4487a0d6ee68aaac81fd8209` | `b4f6eefde89aa7f7ba781b207ca994f41372a800adcef8077b189656c8216eb9` |
| `IMP-OPENAI-002` |  | 真相层 FDE-case-library/data/cases.json#openai-002（clon | MIT（FDE-case-library） | 2026-11-12 | `a7689f6b6d4d4cd02cd5c80cebb5125863a3a684b048b82bcd15672796a3b4e1` | `c13883bde484c367639e868c2f3ee2969d8a3bb9a4b19b8084781f24506135ad` |
| `IMP-OPENAI-003` |  | 真相层 FDE-case-library/data/cases.json#openai-003（clon | MIT（FDE-case-library） | 2026-11-12 | `23b9db9ebc9fe361dc0d4544de4e267e5ac98e155e1c58bd0acedbe6f635532a` | `26a4e8299d3db85593fff2d63e358ab97cbef8fc1e74d5080920bddb8b8d8cae` |
| `IMP-OPENAI-004` |  | 真相层 FDE-case-library/data/cases.json#openai-004（clon | MIT（FDE-case-library） | 2026-11-12 | `4b90639a2e826ab9142aedee477b2cc3df1fbd3b84308c2c436c82fc9a25e838` | `2a50d809a3bd3234a2b4eb7091a0443ad0839bab6905fc5d78a28891ee4cde97` |
| `IMP-OPENAI-005` |  | 真相层 FDE-case-library/data/cases.json#openai-005（clon | MIT（FDE-case-library） | 2026-11-12 | `a3beb5762897ff295bf5683e6e1ffab149bd412a7712c836b458a7cec036599a` | `75f24889bb749f4d496bacc22813ef7fd7370e111313cf6cbdbd7b66cca73e64` |
| `IMP-OPENAI-006` |  | 真相层 FDE-case-library/data/cases.json#openai-006（clon | MIT（FDE-case-library） | 2026-11-12 | `be4d731ee7ddd7be5452b40b0ac46c5a07b1ec94fd38358ccc525e5116394c25` | `962c89abefe436a4f354288d3ac40241b763f1bbad154664488e928d9d704051` |
| `IMP-OPENAI-007` |  | 真相层 FDE-case-library/data/cases.json#openai-007（clon | MIT（FDE-case-library） | 2026-11-12 | `f2c2d795c0f99246250e7266aaa9abc8704038df75740f52df0c1235afb8ed1b` | `3b8b7d96d7af891b9dd35439c7356723817f130a090dfd295aa982c0ad23e572` |
| `IMP-OPENAI-008` |  | 真相层 FDE-case-library/data/cases.json#openai-008（clon | MIT（FDE-case-library） | 2026-11-12 | `191babca8e9bd6a245cf0e55371af53015b8cc45db85a6cab306fe576ed564b2` | `c72f03c0966aea327e190c9147034472938d6440ffebe04e8cf496f1cf7e6cf0` |
| `IMP-OPENAI-009` |  | 真相层 FDE-case-library/data/cases.json#openai-009（clon | MIT（FDE-case-library） | 2026-11-12 | `b580ce5cb70c1a89d73d6688d47990f148e499fd58e41c563c14a828acef9519` | `aed6440f0e8269dc66eef5e6e1ad6282ad5aabf1e4c2546972e759fd78f49c01` |
| `IMP-OPENAI-010` |  | 真相层 FDE-case-library/data/cases.json#openai-010（clon | MIT（FDE-case-library） | 2026-11-12 | `fc517b501bfd0b6f32dd0459d462c2fdd3f5dca4fe0e1e53e3817b47bb49cfcf` | `2c85e2eeb0cfe87b6acd76398d0ab20a437492ff1359602c73b4c0a2f0f4aa42` |
| `IMP-OPENAI-011` |  | 真相层 FDE-case-library/data/cases.json#openai-011（clon | MIT（FDE-case-library） | 2026-11-12 | `92c9994b603b1f11a72bf39ca8ae834de367d3b26fa8b72c9eb8808456c9b8ec` | `705227bf75930dccb91256c67bf31a1e3c0f874b1f83027cd0961fe5dfa0872b` |
| `IMP-OPENAI-012` |  | 真相层 FDE-case-library/data/cases.json#openai-012（clon | MIT（FDE-case-library） | 2026-11-12 | `631687cf00a66a1e7646920fb013b6f186c236765a8057f537d4e63e1f082a98` | `5271c7b64ebbff8a58c5b622941d987b60bdb14d03aa2be39e478b6bd57b00a2` |
| `IMP-OPENAI-013` |  | 真相层 FDE-case-library/data/cases.json#openai-013（clon | MIT（FDE-case-library） | 2026-11-12 | `944e046c0f9a4555d832712eca2e9f5d404c9ad6a1c3017fe5eca6e4f4c9cdcc` | `fb0e674967ae7c9ac4eba2db3c6fa9a57caa45c699c27ed7be60f8d32ec5daa5` |
| `IMP-OPENAI-014` |  | 真相层 FDE-case-library/data/cases.json#openai-014（clon | MIT（FDE-case-library） | 2026-11-12 | `f4b6029b4d73c34198ea58f50b2d279a130e869b132ad504444094dc6d829950` | `44f7f9f2d470cfc1eb117bd4784d96bf98d9a26994e09d3b6dde1155f0c49063` |
| `IMP-OPENAI-015` |  | 真相层 FDE-case-library/data/cases.json#openai-015（clon | MIT（FDE-case-library） | 2026-11-12 | `6b250466805104a866a6a6c50c8a52858064f1225b4e928fbf00ed24bbf4bc28` | `687dd9521a41a9d28ef668a9e3799e9df85bbdca19f41e592c30a8115146245d` |
| `IMP-OPENAI-016` |  | 真相层 FDE-case-library/data/cases.json#openai-016（clon | MIT（FDE-case-library） | 2026-11-12 | `d85375381641e532cc222ba822e8e767229dec43d9949126f57f84d2654b2ef9` | `5f3608d0c0b40ae8f20a5251ef104edf31413a3f7ae7011910d9c6fade0c4ec3` |
| `IMP-OPENAI-017` |  | 真相层 FDE-case-library/data/cases.json#openai-017（clon | MIT（FDE-case-library） | 2026-11-12 | `380872675d6a3771480b854b8b7ce91987522c0c76a710875a0baa6b73cbb378` | `ee47d1a2e6af30306c22ffa26108a7031672e12abd3a0d375f41d5e048115817` |
| `IMP-OPENAI-018` |  | 真相层 FDE-case-library/data/cases.json#openai-018（clon | MIT（FDE-case-library） | 2026-11-12 | `2b3e4adc5d6ae6cddac61a97ba8b8c8e82eaeb1c7384b50cb3f6bfc587ed3236` | `c14f38a8c4261132d1c59e9e4aa918bbf797e5161e4c84f0c93f465f917c5290` |
| `IMP-OPENAI-019` |  | 真相层 FDE-case-library/data/cases.json#openai-019（clon | MIT（FDE-case-library） | 2026-11-12 | `a5181e161780d2dde4b9048ef0daefa8064662f9531e9deab9244062538ebf06` | `8a114f46a687eea7a1f5d5a1f9bb6d3bec269f703bfeb5da6f943078723cdec3` |
| `IMP-OPENAI-020` |  | 真相层 FDE-case-library/data/cases.json#openai-020（clon | MIT（FDE-case-library） | 2026-11-12 | `2c99e87b20185136e67bd85a33e3f8d6424cc4aaea826304ccaae70bd61e13c4` | `31048abbca47b4449a7538184e730ed399d37428164a20de7ba35a5d5060be75` |
| `IMP-OPENAI-021` |  | 真相层 FDE-case-library/data/cases.json#openai-021（clon | MIT（FDE-case-library） | 2026-11-12 | `dd07db88d26501bc03891e41554cc8d26b6ab2a441dceee8021693a8ac375a82` | `c531cea0bf87a6aa294bf2e4d851d5411de34db06c638e36333ff035d87b063a` |
| `IMP-OPENAI-022` |  | 真相层 FDE-case-library/data/cases.json#openai-022（clon | MIT（FDE-case-library） | 2026-11-12 | `5f619984fd601542d63535f9c0567762ac90df30f0a6a8ec759ee3226b4911cf` | `86354c9de3a66ce4e3e89a8d5b82b312f96c058499cc7fe2ed1731086805c38f` |
| `IMP-OPENAI-023` |  | 真相层 FDE-case-library/data/cases.json#openai-023（clon | MIT（FDE-case-library） | 2026-11-12 | `fd1e367358d33cb2d718cc013f84cd69cae7f4ea1095e5b55f88eafe0569e47b` | `cf9992db872ad368df9cdac191a6113cb1b9c13fe139653f492a20d7c13e7f80` |
| `IMP-OPENAI-024` |  | 真相层 FDE-case-library/data/cases.json#openai-024（clon | MIT（FDE-case-library） | 2026-11-12 | `6ea3c7883f418d7f4cd288c8d8567a859d4c2160ca62a71ccd1dc34feaccbfbe` | `7dfb83cba66d51acb9bf27bd7bf3072f3893b03594b9f6458ee77abd526141a1` |
| `IMP-OPENAI-025` |  | 真相层 FDE-case-library/data/cases.json#openai-025（clon | MIT（FDE-case-library） | 2026-11-12 | `007c07cebe70a2fca94f58ef9b0c05a0edf93c1f7c88cc73928a535ae0d1c06f` | `52a6769ad85daa4292b64480cfb74819197c6d51c190fec975d6c42f5c178956` |
| `IMP-OPENAI-026` |  | 真相层 FDE-case-library/data/cases.json#openai-026（clon | MIT（FDE-case-library） | 2026-11-12 | `6eb1a5949b91db094509033c141919bedad97e6e4ded2713464e17daeb451bc0` | `77204af0d58c1d138c2f146fbf101b925e086e339861ac0a7d093fee8292c6a1` |
| `IMP-OPENAI-027` |  | 真相层 FDE-case-library/data/cases.json#openai-027（clon | MIT（FDE-case-library） | 2026-11-12 | `e48c126df9084773d47fd3912a5cfb760b5db8ad69a431160578ba985e278207` | `8a496853b43c080cecde1593a55126d1616c4c32bdecff129fd6121d4325df7e` |
| `IMP-OPENAI-028` |  | 真相层 FDE-case-library/data/cases.json#openai-028（clon | MIT（FDE-case-library） | 2026-11-12 | `28df888026ec259d70afdbd044069c67265acd50b00102dfd7bc71cc0debe12b` | `743bbd6fc08c2d57ef2ec4ef9095874742faeef8e31884efcd799bcc36a62995` |
| `IMP-OPENAI-029` |  | 真相层 FDE-case-library/data/cases.json#openai-029（clon | MIT（FDE-case-library） | 2026-11-12 | `f9ee5a0275268dc80853a485e40c0939326c6905ad6ca8d9a324506310f82ec8` | `f5b1c22bd589284e5123f91cdff816201fe6627fecbc7cd153286f87a4bb6391` |
| `IMP-OPENAI-030` |  | 真相层 FDE-case-library/data/cases.json#openai-030（clon | MIT（FDE-case-library） | 2026-11-12 | `f48c56b4a82a4c6ce11f0ac0e2f048d1a407431d7f7924d77cde45f546d81f3e` | `01c05910cceda578a65c726ff7c556386635888c1fe210f0b7feb19cd9bfef29` |
| `IMP-OPENAI-031` |  | 真相层 FDE-case-library/data/cases.json#openai-031（clon | MIT（FDE-case-library） | 2026-11-12 | `e951a1e264223ca00a2853670e5d20beb49ab8e40430ff4a021da04fc75f9b61` | `ab8c777c184e6bf04971080dce6afa0a6573c6fac9118028c3fba8469966eb7a` |
| `IMP-OPENAI-032` |  | 真相层 FDE-case-library/data/cases.json#openai-032（clon | MIT（FDE-case-library） | 2026-11-12 | `8109436f5a715db05382f8af498e57753b55921ed9c5c91e9cd4c0fffbd95fd1` | `faf7a8b44b884906e9e367201ef85ce2711aef274cf3c7fdc853eea50be85d0d` |
| `IMP-OPENAI-033` |  | 真相层 FDE-case-library/data/cases.json#openai-033（clon | MIT（FDE-case-library） | 2026-11-12 | `25a6117740517e2185daa99c5fff1c057a33c731284a2b07cb61826445e5eadd` | `e573345f1c2304e6ad018338adef7eda2d5a039623a59fb521d790fe89412ec9` |
| `IMP-OPENAI-034` |  | 真相层 FDE-case-library/data/cases.json#openai-034（clon | MIT（FDE-case-library） | 2026-11-12 | `34a1d848f7cf01f9fc92c81be743f10a612378d2696428d9d395a10e2fda6388` | `9000b5d5d64ab04d8b88bf72cc3e1ddc4112b1dbf98de8e1a7b09f93979f5a9e` |
| `IMP-OPENAI-035` |  | 真相层 FDE-case-library/data/cases.json#openai-035（clon | MIT（FDE-case-library） | 2026-11-12 | `9dac213a0ace0c69a5b1d6dab1e4cd4933028fa21f2f543f7cac00c03bfda012` | `d04af0e492f5e2f3914b24f99d4d5b39cfab9fc78bf82208c664895e8d24fbb9` |
| `IMP-PALANTIR-001` |  | 真相层 FDE-case-library/data/cases.json#palantir-001（cl | MIT（FDE-case-library） | 2026-11-12 | `ab1e44a94a34b4e61126c80031725bed02ed63669830ab40cfdf1faf27bd83be` | `adabc791c3590dcfce516ee2866c1b018dffc29607ed643260b0afe675107bca` |
| `IMP-PALANTIR-002` |  | 真相层 FDE-case-library/data/cases.json#palantir-002（cl | MIT（FDE-case-library） | 2026-11-12 | `44d6a6a3021dd4e22e864924f80fbc4bcb0b515160e52040c50f0a2fd16ccd09` | `dee26592053d5b1f861070f4acb173e9ac7670159de174aa21671da8ca2cad26` |
| `IMP-PALANTIR-003` |  | 真相层 FDE-case-library/data/cases.json#palantir-003（cl | MIT（FDE-case-library） | 2026-11-12 | `4c30d318f55cc7171cc1361b535c2208d44b8e840371f030c413d966ffff0321` | `aed46950af2a7aac9c4f2a134a70d2a18965fd7053ed72b9b9b6de406a5d7074` |
| `IMP-PALANTIR-004` |  | 真相层 FDE-case-library/data/cases.json#palantir-004（cl | MIT（FDE-case-library） | 2026-11-12 | `6d9a4a1269c530fed7554506e9be8b58ca289bdf3a046cdfdfff835ef9d68c50` | `0f651d40a9a027ef4619b0fa78e21a9d51227918f90c682809078ab68991a11b` |
| `IMP-PALANTIR-005` |  | 真相层 FDE-case-library/data/cases.json#palantir-005（cl | MIT（FDE-case-library） | 2026-11-12 | `e7cba925a51ba1915df24244e8efb18230b227612cecf193ea9025dff0cd36f5` | `16fb2bf391f0a586fce0f152541cddfee38fd870349703ba7809bcbf3958fe98` |
| `IMP-PALANTIR-006` |  | 真相层 FDE-case-library/data/cases.json#palantir-006（cl | MIT（FDE-case-library） | 2026-11-12 | `88f9a57a511c4f47fef2c4c3d1e26cc5382c65ad9dfa8edb14b30f3613db6a14` | `d4ea630bb903ac8cc7f388e4e5f55d1c8ac2c9dbb9583e43090c7f21768e9623` |
| `IMP-PALANTIR-007` |  | 真相层 FDE-case-library/data/cases.json#palantir-007（cl | MIT（FDE-case-library） | 2026-11-12 | `04b6d623a1d6b1ec814af0e36d94baace3ded08c531ce346f2f6665914444543` | `215c7e62db10ac37796655d0f11d749f09221c073c00b52f88fea38f49bdeb2c` |
| `IMP-PALANTIR-008` |  | 真相层 FDE-case-library/data/cases.json#palantir-008（cl | MIT（FDE-case-library） | 2026-11-12 | `dfc2db0e5f4a44a2db94ac9742a433371e9b77b89b8f969053e2c6ab8faadcab` | `3310a3fcc0a7538f403f3518b6f5d3a1520a5a0d64c06cbbeb2fe00aef8dd4a9` |
| `IMP-PALANTIR-009` |  | 真相层 FDE-case-library/data/cases.json#palantir-009（cl | MIT（FDE-case-library） | 2026-11-12 | `6d9c1eb9191a90a7daa9612cf70e92ea0bfdfa725ac50c1c4d0a512b5ad17092` | `bf5a1ac8bf2f26a6b4e88a853e2ef270d09bb73cc2fd12ddabbc3de494a6bdd4` |
| `IMP-PALANTIR-010` |  | 真相层 FDE-case-library/data/cases.json#palantir-010（cl | MIT（FDE-case-library） | 2026-11-12 | `cc7f8d7bb766e0680bb30207a5492ee2ac50a882ba574598c1b703e14f1501bf` | `ef8cfcfe8d6fde9e1c50d72d52cf44aec2c804314c826b32c19c5b1dbbcd6784` |
| `IMP-PALANTIR-011` |  | 真相层 FDE-case-library/data/cases.json#palantir-011（cl | MIT（FDE-case-library） | 2026-11-12 | `cce69455e89004a5656a282fb6c4ab786d5e99b37f1208152e8846e095e48379` | `2e1025d21435c6874463df3fde54b63fa831bd6dbe7f8da9f067df6e1bb8ab7c` |
| `IMP-PALANTIR-012` |  | 真相层 FDE-case-library/data/cases.json#palantir-012（cl | MIT（FDE-case-library） | 2026-11-12 | `1f4c0550808d7e6b2bc6581e7db4d8fe6d128fdcd1d994788d20eed3bd870d2b` | `1778ed0a5090e5c0199310afe13d026ea48a6368bdb0ed688e613a3e319de9f9` |
| `IMP-PALANTIR-013` |  | 真相层 FDE-case-library/data/cases.json#palantir-013（cl | MIT（FDE-case-library） | 2026-11-12 | `0657bd3b77608363ca80e37f1b5e2daa40511e3fd0a2df920f6638cd84d43e34` | `ec0401fe07939be69ea184e32c0f411d471dd5bc147ae5d1248bf97946952efb` |
| `IMP-PALANTIR-014` |  | 真相层 FDE-case-library/data/cases.json#palantir-014（cl | MIT（FDE-case-library） | 2026-11-12 | `409b676ab5098d8c646da7a92aab32ac38a83eb6551e468e018568a2f078afe3` | `724f548b1b6529cd714c7d830926d350a9b2b3630b9a23d9f444fe985ff7eefe` |
| `IMP-PALANTIR-015` |  | 真相层 FDE-case-library/data/cases.json#palantir-015（cl | MIT（FDE-case-library） | 2026-11-12 | `8be4e0f502ff522d226bcb29c73c399961c396a11f0d340dcf18b33212a9cd7e` | `87b10706512b68113dea9c2c509d00b201df45a6991adcd4ba567d045ce7275b` |
| `IMP-PALANTIR-016` |  | 真相层 FDE-case-library/data/cases.json#palantir-016（cl | MIT（FDE-case-library） | 2026-11-12 | `b8641fbddfd5d285b41ee512f3fc08bea20d34507ec242d09e4c8078561b8366` | `dc9700cd9df5221cf5d4082cbe9ade9f8f8f04b87ad464c97fe3cf244d542491` |
| `IMP-PALANTIR-017` |  | 真相层 FDE-case-library/data/cases.json#palantir-017（cl | MIT（FDE-case-library） | 2026-11-12 | `b3902e7abf7f743ce64b3e8a240c39ab0976c26b56e86db491354afde3316b1b` | `82e1bf07a674087ed57966da6d044591947dbf5d29f2f98c65b5be9b1a342bd2` |
| `IMP-PALANTIR-018` |  | 真相层 FDE-case-library/data/cases.json#palantir-018（cl | MIT（FDE-case-library） | 2026-11-12 | `344d3313e6051b98cdccc08ccc3fa874da83c7eb7be279ae93efa8d3f867c3d4` | `a34cd5512ad4f008593b74f517438622c9478155ed6fa8ac5379199910d805a7` |
| `IMP-PALANTIR-019` |  | 真相层 FDE-case-library/data/cases.json#palantir-019（cl | MIT（FDE-case-library） | 2026-11-12 | `0596a19bd7aa7e9c1737881e2e79974b846ded8450ca3391b0a1b2da39817117` | `50d975bc98455c33e59e6ac1a6196baa8b446c4380c6c8cc942ba1184ff6ebdf` |
| `IMP-PALANTIR-020` |  | 真相层 FDE-case-library/data/cases.json#palantir-020（cl | MIT（FDE-case-library） | 2026-11-12 | `76859042868dc743a5ba474b355a11c4748b35692e3046c75c181f5e52818ffc` | `d3a9515089991b20fd48c2439493eaf2144b6b66d6feff3c5633396659e1aae1` |
| `IMP-PALANTIR-021` |  | 真相层 FDE-case-library/data/cases.json#palantir-021（cl | MIT（FDE-case-library） | 2026-11-12 | `71bc456553255e8f6df9712987f0019b55fe088cb566a16477973410239e3951` | `e249b87369430ce2c34f9fe5dea0bd83f2ebc354170e4e911efad5dd8c01fd8d` |
| `IMP-PALANTIR-022` |  | 真相层 FDE-case-library/data/cases.json#palantir-022（cl | MIT（FDE-case-library） | 2026-11-12 | `1536ba33ae40be8b4e7b786ee429fafe4e5c909faa7532eda89e1987d4fccf65` | `fb6a719d0252362f7d9052e9ec4cdb15cc8ca640e252ec0a5739839aa936aab3` |
| `IMP-PALANTIR-023` |  | 真相层 FDE-case-library/data/cases.json#palantir-023（cl | MIT（FDE-case-library） | 2026-11-12 | `54035dcd82e055d94e612982640877eb3446729946595c397ebf47b442ba3cbf` | `5a211005bdb5bcdec7245babefb8df61804638c295e798bfec7c5a5d546b1cd6` |
| `IMP-PALANTIR-024` |  | 真相层 FDE-case-library/data/cases.json#palantir-024（cl | MIT（FDE-case-library） | 2026-11-12 | `685747ce06baa55a7d5863c8c16b2b3b7ba891a784faabbfe4e9b7cc83985bb6` | `d027f186a107c99a2eef4108ec5f96ff4f0379873215cbf3be3f50ccf23c6a2e` |
| `IMP-PALANTIR-025` |  | 真相层 FDE-case-library/data/cases.json#palantir-025（cl | MIT（FDE-case-library） | 2026-11-12 | `61bdd3fc69c5316b6fadfa615772badc975b966b1af1bc66cbeb637ea17002d7` | `6a386aad49e00b6fe942f6eab79a11bd1f85f7c3556cbfcd7905762fd61e3dce` |
| `IMP-PALANTIR-026` |  | 真相层 FDE-case-library/data/cases.json#palantir-026（cl | MIT（FDE-case-library） | 2026-11-12 | `1088ceea997abc3dc8c7602ff712fd1724c1ffbd95a0d1e556460b4b0643d496` | `683d6d0fa2f0d406aff97943154a867296fe50a9764a2cfbf53ea06a0640f91a` |
| `IMP-PALANTIR-027` |  | 真相层 FDE-case-library/data/cases.json#palantir-027（cl | MIT（FDE-case-library） | 2026-11-12 | `64bbbce0abfc5965757f22b0319489060c2097ed46eb70318977ad8ddd8c1d52` | `ac09c1b30528e9268e0138cc38f76ab7ebac176f8a1ada3057769a5328471819` |
| `IMP-PALANTIR-028` |  | 真相层 FDE-case-library/data/cases.json#palantir-028（cl | MIT（FDE-case-library） | 2026-11-12 | `b4d0c9a121effe2895eb6c35b2dcf9bb4ebf833e2e6ce5d9039a3afe8fafb967` | `76279a13719266c11805aae9678c3d53d44e41f616b16e061179777db0097e3c` |
| `IMP-PALANTIR-029` |  | 真相层 FDE-case-library/data/cases.json#palantir-029（cl | MIT（FDE-case-library） | 2026-11-12 | `53dc651922e6a59c983ec3f12f46b6dbee0b0e17412aed2084e5b89f4a89aebc` | `54964afd4350929ed157e0a5918fc18ce3d065bd839e961b4c06472e1a527c82` |
| `IMP-PALANTIR-030` |  | 真相层 FDE-case-library/data/cases.json#palantir-030（cl | MIT（FDE-case-library） | 2026-11-12 | `b70faf155a9ae9b564f51271d3deee2e1db166e6d89d405a85713b1d54e72c80` | `b674588d53b6b5bf9ae3ee067e089cfcb8e9831c442aa42d2d98c268af417a1f` |
| `IMP-PALANTIR-031` |  | 真相层 FDE-case-library/data/cases.json#palantir-031（cl | MIT（FDE-case-library） | 2026-11-12 | `4911563330a513d913e774ee874e89546982b535f8c3e21f0061de7c71d32f64` | `156a3d000dd7977942025b55396eedee13e351ad31a2ab08365467edb57a7502` |
| `IMP-PALANTIR-032` |  | 真相层 FDE-case-library/data/cases.json#palantir-032（cl | MIT（FDE-case-library） | 2026-11-12 | `52de599aa20b25b0c4744719ba9ce5f09781d107f721b56e76965fb424d7cc22` | `f241ce8ff4d1058bdbfca8fecb283ced30549f163188c5eb998b2ad9f8716df9` |
| `IMP-PALANTIR-033` |  | 真相层 FDE-case-library/data/cases.json#palantir-033（cl | MIT（FDE-case-library） | 2026-11-12 | `d29ff9d4fbbbd17d9a867c22688bfdce610d81d008edd512032dc353b6ac22e5` | `b7461cce3a2c744ebee03ff032009ef4b693f729507573f75007b3d22824e6e3` |
| `IMP-PALANTIR-034` |  | 真相层 FDE-case-library/data/cases.json#palantir-034（cl | MIT（FDE-case-library） | 2026-11-12 | `76554c0afb64ed64055c6a63562ea823c2b11d587680bb4683888ac26834d7d7` | `3939c248fb2f2cbb5eea3556f5cc41c87b67724433e1b0705b873510798e8461` |
| `IMP-PALANTIR-035` |  | 真相层 FDE-case-library/data/cases.json#palantir-035（cl | MIT（FDE-case-library） | 2026-11-12 | `b933b0868f402684a43236d7d68d71f87b173f1c4db6f2c68dd2c43de263cf8a` | `0aa127b8917eefbe546fb88b993d37c7792d3e516b5ccc6f1747c060503ef66b` |
| `IMP-PALANTIR-036` |  | 真相层 FDE-case-library/data/cases.json#palantir-036（cl | MIT（FDE-case-library） | 2026-11-12 | `c8f9202fb034de9d6a84d05af419d5697190ecf9aa60aaca9cbfece501f65034` | `71f59ea8ac7d4c1332aa648a43f32e89046eef89785f80ffe04b17fbbc74b896` |
| `IMP-PALANTIR-037` |  | 真相层 FDE-case-library/data/cases.json#palantir-037（cl | MIT（FDE-case-library） | 2026-11-12 | `4d923ec7414869e97603d4808a1543ce88e01319fec014a979d078355a41f8c0` | `aca0528f279072a0903cb9a0a7fa82dacbc30d49bb91481c24af69a0ecf665f8` |
| `IMP-PALANTIR-038` |  | 真相层 FDE-case-library/data/cases.json#palantir-038（cl | MIT（FDE-case-library） | 2026-11-12 | `8f5c25e8376c9a76c647839623335f21d89cfc6e93a93963d0ffd1e6a8ec92e9` | `f0cb655b6ecccd316cf3a63e158e41c3d01c4ff8335f8f8e6309716ed391a07e` |
| `IMP-PALANTIR-039` |  | 真相层 FDE-case-library/data/cases.json#palantir-039（cl | MIT（FDE-case-library） | 2026-11-12 | `b2498911194b1f4dafe1a1dc9d8d182e06565865fe88f62af37483042b7b653a` | `cbb11ecc4029e3aab6d8d41b36041bb2133b712bd8157f6a07f0895a5d7ce972` |
| `IMP-PALANTIR-040` |  | 真相层 FDE-case-library/data/cases.json#palantir-040（cl | MIT（FDE-case-library） | 2026-11-12 | `e96fa51d1ba3ed545eed5ab766fad3b415419fc6b684103733d21d8c5f427d23` | `bd93bc4f54e83e2cff4cbf587776482bfb432860d3e5f427a971cb3b63642f71` |
| `IMP-PALANTIR-041` |  | 真相层 FDE-case-library/data/cases.json#palantir-041（cl | MIT（FDE-case-library） | 2026-11-12 | `22b88d1bcf0aa29a2a82e0117fbfabf1a70b5db220d9d06b3d68d5fa3f72a317` | `9526eb68528b94dc63e7ce34ed090c3d779611c89b3a01c15b6f92d57017f90f` |
| `IMP-PALANTIR-042` |  | 真相层 FDE-case-library/data/cases.json#palantir-042（cl | MIT（FDE-case-library） | 2026-11-12 | `590cb3fec887f725673f0cf8a5764bf9633ed504fd992f5823654848c0c76460` | `08f5f4d894797535e5ef8511251a0fd5afab9b4f5c3028a9194e3cebcbf0ccaa` |
| `IMP-PALANTIR-043` |  | 真相层 FDE-case-library/data/cases.json#palantir-043（cl | MIT（FDE-case-library） | 2026-11-12 | `80dd35fd92d3957a84daa4605b3b5650f07bcd300b16b92f127b26e724161dda` | `8dbce321d4025cc748743435d811f72423038d645712f1fc913c91b41a770f26` |
| `IMP-PALANTIR-044` |  | 真相层 FDE-case-library/data/cases.json#palantir-044（cl | MIT（FDE-case-library） | 2026-11-12 | `d9c08cc2ea201a3abc0ec08604eb861feba5b98bedcb91037017b630fe50fe3c` | `44b86b3c30c935cf90f1efd737ad98e39ed579fe043d3c52b398c6351528acd1` |
| `IMP-PALANTIR-045` |  | 真相层 FDE-case-library/data/cases.json#palantir-045（cl | MIT（FDE-case-library） | 2026-11-12 | `8d8b6c9b7b285ec6fb6724758db900a2a6ea25c6980d9ff73313159ab680808a` | `5814894e14d38d65741b58189f7ecb45a7ab73cfc3a959452eeae7075033007b` |

### 1b. 文集 B 演练训练场 7 卡（无许可源严档仅思想，原创场景）

| scenario_key | 主题 | 来源指针 | 许可 | 快照 | 包 sha256 | 卡 sha256 |
|---|---|---|---|---|---|---|
| `IMP-FRK-DEMO-CRISIS` |  | 真相层 文集 B（无开源许可技能文集）「实战演练篇·现场演示抗压演练」思想条目；仅思想/方法借鉴 | 无开源许可（严档仅思想） | 2026-11-12 | `dd22e1ba97760673b67d93b897f72bf31fb6dd9de0ff3d627fecc3c638d2dd9f` | `815aa184db1514f6039a2ad6cc8cca32a5b4ae60546db884d62fd029b963f690` |
| `IMP-FRK-EXEC-BRIEF` |  | 真相层 文集 B（无开源许可技能文集）「实战演练篇·高层汇报演练」思想条目；仅思想/方法借鉴 | 无开源许可（严档仅思想） | 2026-11-12 | `3c367ebc49f3e3ba70003235bbc8f385151f95bfe9b7e57dddc19c01bd9a4ad6` | `f412cbbe771a761564d42a5575519cadc01cc59cddecaf97976b23f425d86245` |
| `IMP-FRK-NEGOTIATION` |  | 真相层 文集 B（无开源许可技能文集）「实战演练篇·商务谈判模拟」思想条目；仅思想/方法借鉴 | 无开源许可（严档仅思想） | 2026-11-12 | `e43fe266e7a7f937cb8a2d97bae46cc04c1880adc3cedb6b88a1749cb3575b62` | `34ff2217962a4e7015b9f040e64786130543d762dc1e9eb4d15b149c4c5390cc` |
| `IMP-FRK-OBJECTION` |  | 真相层 文集 B（无开源许可技能文集）「实战演练篇·客户异议抗压演练」思想条目；仅思想/方法借鉴 | 无开源许可（严档仅思想） | 2026-11-12 | `c7bef8329bb1297d1778d62cdedf69a52dbd343267e7aee381148ebb1fae62a0` | `1e8806dfe3840804bb7d54f5f808d698dcfa8eb7805b58f506b34b4ef7f56394` |
| `IMP-FRK-REQ-DECOMPOSE` |  | 真相层 文集 B（无开源许可技能文集）「实战演练篇·需求拆解演练」思想条目；仅思想/方法借鉴 | 无开源许可（严档仅思想） | 2026-11-12 | `6465661b519472f32bd3b44548f74648dd71a46c12173e9ff2e379141bb7031a` | `96272f41aff18a4d06773b754916ec53f2503bd9fa40801d68016dda399b70c3` |
| `IMP-FRK-RETRO-DRILL` |  | 真相层 文集 B（无开源许可技能文集）「实战演练篇·项目复盘演练」思想条目；仅思想/方法借鉴 | 无开源许可（严档仅思想） | 2026-11-12 | `f999eae194eb5dd297c70d5848b776531bd82479538304d042207eb4ab0d4004` | `cd689e51252180eee76ec986b78c1f0cc291e5a3256ed687144b84e152661420` |
| `IMP-FRK-SANDBOX` |  | 真相层 文集 B（无开源许可技能文集）「实战演练篇·全项目沙盘演练」思想条目；仅思想/方法借鉴 | 无开源许可（严档仅思想） | 2026-11-12 | `8133755719ac3dd02c2bf3477161095c2cd621c94b16ba5971e5594bd11c0875` | `6675424f39621192b961c0710de91aeeef55283b2fbaa52083da395bada76baf` |

辅助件：合并批次件 packages\import-batch-20261112.json sha `5f9723124d7e64fd9d6caa5ee6a1b4d8bef3c21e1b8a4ffa8c059198a4c51d93`；`manifest.json`（转换器生成，时间戳 2026-11-12T17:11:57.998683+00:00）。

总包数（逐卡）：134 ＝ 卡24 127 ＋ 文集 B 演练 7。
## §2 B#35 来源对照表（独立改编声明，评审可否决等价复现）

| 家族 | 源条目 | 只取的抽象层 | 明确不取/弃用 | 重写产物 |
|---|---|---|---|---|
| 127 例（卡24 家族，`IMP-<案例ID>`） | 卡24 案例库各条目（MIT） | problem·solution·human·reusable 的抽象打法与判据维度；问题—方法—治理三层映射到训练场三视图 | 条目级清单与结构化表达；源条目公司名（任何字段零出现）；源效果数字（幅度一律以客户自身基线测量为准） | 自有结构：画像/三句简报/3-4 条隐藏事实（情境与前提，非答案提示）/判卷基准三桶 |
| 文集 B 演练 7 件（`IMP-FRK-*`） | 无许可文集 B 实战演练篇思想条目 | 仅思想/方法：生命周期连续决策、复盘五步、异议情绪先行、演示应变套路、谈判底线与交换式让步、需求病理四分、高层汇报三要素 | 全部结构化表达（场景卡台词、分级表、分钟级模板、时段分配表、评分表、阈值数字）——零复现含等价复现 | 全原创场景：情境/角色/隐藏事实/判卷基准均自写（如 IMP-FRK-SANDBOX 的知识助手全链沙盘、IMP-FRK-NEGOTIATION 的续约扩围谈判） |

许可复核义务：MIT 状态本表登记快照 2026-11-12（远端 HEAD `ef55012` 与本地零漂移）；文集 B license=null 2026-11-12 复核 404。红线第 8 条④：远端 LICENSE 或 HEAD 变动即复核。

## §3 时效复核（红线第 8 条④，2026-11-12 当日实测）

- 卡24 案例库（MIT，guminghao-avi/FDE-case-library）：本地 clone HEAD `ef5501231b60539e91c770437a2bfd7c60d65277`（2026-09-23）＝`git ls-remote` 远端 HEAD 逐位一致，LICENSE（MIT）无变化 ⇒ 快照有效。
- 文集 B：GitHub license API 实测 404 ⇒ 无许可严档维持（与 batch-3..8 各批口径一致）。
- L1 首批 4 包不受本轮影响（独立目录、manifest 各自独立）。

## §4 人工闸三步（蔡工亲做，AI 不代发起）

1. **审阅**：逐卡读 `D:\test\FDE\knowledge\交付场景导入包\round2\cards\*.json`（或逐包读 `packages\*.json`）——重点核对 hidden.facts 与 reference 判卷基准是否符合交付口径；134 件全为 `status='draft'`。
2. **导入**（建库行 `draft`；走 API，与 L1 首批同款）：
   ```bash
   # 登录取 token（桌面同账号）
   curl -s -X POST http://127.0.0.1:8010/api/v1/auth/login -H "Content-Type: application/json" \
     -d '{"username":"<蔡工账号>","password":"<密码>"}'
   # 逐包导入（或用 packages\import-batch-20261112.json 一次全量；逐条回显，非法不阻断）
   curl -s -X POST http://127.0.0.1:8010/api/v1/simulation/scenarios/import \
     -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
     --data-binary @"D:\test\FDE\knowledge\交付场景导入包\round2\packages\IMP-SANDBOX-SAMPLE.json"
   ```
3. **核对＋激活**：桌面训练场→案例库逐字段核对；确认后 `PATCH /api/v1/simulation/scenarios/{id}` 带 `{"status":"active"}` 激活（追加新版本，旧版不可变）。**语义质量（判卷基准是否贴合交付口径）以人工审阅为兜底，与本轮登记的形状级闸门分工明确。**

## §5 验收记录（2026-11-12 现测；勘误事件见末条）

- **四闸多轮独立实测全过**：①主会话本地（初版）134 包／失败 0；②工作流复核轮 134/134 零发现；③工作流复跑终闸（01:09）127/127；④主会话勘误复核（01:11）134 包／失败 0——各轮结论一致。
- 装配器骨架装配：127/127（missing=0、invalid=0）；起草块形状零违规。
- 污染隔离：本轮零接触诊断评测答案（评测答案目录零触碰）；单向阀口径不变（判卷基准只进训练场 judge 面）。
- **未做（恒人工）**：draft 建行与激活——AI 不代发起、不碰 API；134 包全部 `variant='normal' / source_kind='import' / rubric_version='rubric-v1' / split='train'`，vague/complex 变体留训练场变异机制按需物化。
- **登记勘误事件（2026-11-13 晨如实登记）**：初版登记（PR #400，表基于 21:02 manifest，其中 33 例为主会话补齐的过渡态）之后，原起草工作流在 provider 用量窗口重置后**自动续跑**，写手终稿覆盖同批 42 例（登记时的 33 例主会话补齐件＋9 例停摆时在飞件）并于 01:09 重过四闸；batch-13 与文集 B 演练 7 件未受影响（92 例与初版一致）。**本表已按终版 manifest（主会话 01:11 复跑复核，134 包／失败 0）整体更新**——42 行哈希变化、92 行不变；辅助件 sha 相应更新。防再发：该工作流两 run 均已终态（completed），无再续跑可能。
- **登记-修订链**：#400 初版登记 → 本 PR 勘误（v2 表）。

## 已入库状态（2026-11-12 实测）

- PR：[#400](https://github.com/caishide/fde-workbench/pull/400) 已 squash 合并（`dd67732`），CI 8 check-runs 全绿；回填 [#401](https://github.com/caishide/fde-workbench/pull/401)（`0fbd98f`）。
- 包体持续留真相层 `round2\`（不在仓内）；draft 建行与激活待蔡工按 §4 三步人工执行。
