# 导入轮第一批清单与指纹（L 线 round2：卡24 127 例＋文集 B 演练 7 件，2026-11-12）

> **性质**：登记表（ks1 线挂账消解——训练场挂账与卡24 127 例导入排期销号件）。上游：batch-2 拍板②（卡24 127 例排进 L 线导入排期）、PROGRESS「训练场与育才挂账」节。
> **纪律**：导入卡与导入包（含判卷基准）**全部只存本地真相层**（`D:\test\FDE\knowledge\交付场景导入包\round2\`，与 L1 首批的 `cards\packages` 目录隔离），本表只登记指针＋sha256＋许可快照——仓库被扫面零判卷材料。
> **转换器**：`scripts/simulation/import_cases.py` 四闸（卡 schema 允许名单 → `validate_scenario` 八规则 → `load_view` 三视图泄漏自检 → 输出目录仓内拒绝），**两轮独立实测 134/134 包全过**（主会话本地一轮＋工作流复核轮一轮，结论一致）。
> **起草来源**：127 例＝卡24 案例库（MIT，见 §3）条目独立改编——94 例由起草工作流产出、33 例由主会话按同一提示词契约补齐（红线：企业名一律代号化、源效果数字零写入、全中文、判卷基准为方法论判据）；文集 B 演练 7 件＝无开源许可文集 B 实战演练篇**仅思想层**原创重写（零条目清单/分级表/分钟级模板/阈值组合复现）。

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
| `IMP-DATAWHALE-005` |  | 真相层 FDE-case-library/data/cases.json#datawhale-005（c | MIT（FDE-case-library） | 2026-11-12 | `5db9865d43d0e22c91af40e0d385f31d0b399288b95e55ab38121f706ec20fa1` | `135c986c781c4816fe624bdfcf0ffb25210335360492e965c736ff377795c2a2` |
| `IMP-DATAWHALE-006` |  | 真相层 FDE-case-library/data/cases.json#datawhale-006（c | MIT（FDE-case-library） | 2026-11-12 | `e6dc178a674a7cbcdeb776ee780cb0afdf8732c7e583202f009e863588d10543` | `2486df6360cf48b73000f63da68ffaeaa36adad13f7506b8c1e83d91b6e98c26` |
| `IMP-DATAWHALE-007` |  | 真相层 FDE-case-library/data/cases.json#datawhale-007（c | MIT（FDE-case-library） | 2026-11-12 | `0f3be7c83f24f41d4101640e1a09531c3249d0944f6dcbf285274e0eb04c9148` | `7d6386c147f6e819e4298536f03f52fbb79490ce6bff115e9b6ac21ecf2607d0` |
| `IMP-DATAWHALE-008` |  | 真相层 FDE-case-library/data/cases.json#datawhale-008（c | MIT（FDE-case-library） | 2026-11-12 | `c67a8b0f80d084c3170e62f4c29697b518357e6b9047991a497a3166d9bb2c86` | `429d85e0e48b2a991c123a4c29a4c2f97f9d66afd5d12e84d49273625b791195` |
| `IMP-DATAWHALE-009` |  | 真相层 FDE-case-library/data/cases.json#datawhale-009（c | MIT（FDE-case-library） | 2026-11-12 | `0256cf4bb057bf6f4ca37b0c5595ceeae9678e5886bf363aa750a318ac60dd3a` | `32a085d16e2f9fa2e41b318a3397c5414309d1d70147069957c5832db10057f2` |
| `IMP-DATAWHALE-010` |  | 真相层 FDE-case-library/data/cases.json#datawhale-010（c | MIT（FDE-case-library） | 2026-11-12 | `53d98077b023274d0152acf349a2a9bce0407581f7f9536477d31deb2c3b8dd6` | `a47427ce98590af28b95c91ad62d4dd377b2ed11ef4c04d146ee12a24221ba58` |
| `IMP-DATAWHALE-011` |  | 真相层 FDE-case-library/data/cases.json#datawhale-011（c | MIT（FDE-case-library） | 2026-11-12 | `2c50308f9eb086cefebbb9e7161632d4adcb84ce56d03549a8f0166cfaa4ac5c` | `ad508b1627e57e3aa940cb29141c636240eee45eb3798fb4f1220f2c601a6467` |
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
| `IMP-ENTERPRISE-NUBANK-SUPPORT-AGENTS-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-nuba | MIT（FDE-case-library） | 2026-11-12 | `318f99ec2c3aca39798a09118b4f29fc26de7771895ab503fb298a40730875a9` | `79d13e375af6e27f3f000141065f5c88fe07b10e3a84fac13659bce144040d46` |
| `IMP-ENTERPRISE-TELSTRA-AI-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-tels | MIT（FDE-case-library） | 2026-11-12 | `c2abf93ac3fbed4a5fcbf86f74a9a9e868c89ab78866afc7832553d08bc1ff2e` | `7d09d33bf355827e644ccf296d98b19741399e4603145a234c788f52d4dd5839` |
| `IMP-ENTERPRISE-UBER-GENIE-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-uber | MIT（FDE-case-library） | 2026-11-12 | `015b7a3e302fcc7106df79b4ac92bf2b4344609ee791c52ce3cdef621e827748` | `3f69d6bdcdcc3eea55450210b3e1cdb4cf8c08d66d2e2262dd56f7762239078b` |
| `IMP-ENTERPRISE-VODAFONE-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-voda | MIT（FDE-case-library） | 2026-11-12 | `376cd62dc0329b1a39b7f942e4a8704cb1c9fa5c7c6cea5fb026bd49f37980f1` | `49d67ae94914f9f80c31084ad01aaebbdfd9ec548a95912631ea747f46d60d39` |
| `IMP-ENTERPRISE-WALMART-001` |  | 真相层 FDE-case-library/data/cases.json#enterprise-walm | MIT（FDE-case-library） | 2026-11-12 | `2beb1407b76e73674dd4dbddd8040c45d517f2cde2ec4699f33d151998dfb239` | `957ffc41de695f88a3dfe1d180ea7ec70471053d99bb7eae33af0acf5af9ad94` |
| `IMP-GOOGLE-BERENBERG-001` |  | 真相层 FDE-case-library/data/cases.json#google-berenber | MIT（FDE-case-library） | 2026-11-12 | `07590a8cfca7b5f4ffd824a4d8d4a62035fcf18647be0ac4053bf531c663c633` | `cc4405682055a1c4fadb9d2fa7cfc8f65c41f3e1d98cca0f2970b55ce193522c` |
| `IMP-IBM-LOCKHEED-MARTIN-001` |  | 真相层 FDE-case-library/data/cases.json#ibm-lockheed-ma | MIT（FDE-case-library） | 2026-11-12 | `3733fc9e53c77f8493357148db990a79fd7e6c627139d82c6c4bf2da97ac7e7f` | `7a13c5ae99008c5783030e5483a103873273bd3a2d815ec11cd41022eafda906` |
| `IMP-IBM-MEDTRONIC-001` |  | 真相层 FDE-case-library/data/cases.json#ibm-medtronic-0 | MIT（FDE-case-library） | 2026-11-12 | `1a7962e747c1d9c7f805436b1a57ab4f030d744cc87f3a11e794d825dccd4d71` | `f4d37d55c6487ebba2e365da1ae7a88d11e8606f6506f4dc29e7ba4563bd16f0` |
| `IMP-MICROSOFT-PRESIDIO-001` |  | 真相层 FDE-case-library/data/cases.json#microsoft-presi | MIT（FDE-case-library） | 2026-11-12 | `ae9dcee7c81356930bcb456110d35045462076a355e4676fbd32bc1b4dd332cc` | `00c0b107d60c6f283743ab14053b1009a6b9a72adcabf4c0e84efc60dde308f6` |
| `IMP-MICROSOFT-ROLLS-ROYCE-001` |  | 真相层 FDE-case-library/data/cases.json#microsoft-rolls | MIT（FDE-case-library） | 2026-11-12 | `d69bcca2ba1fa3efac2d6e003d1f6112241a17426ae06e8f2459cee33aaee6ec` | `f5aeb0acde3711195513c377b40ebb52e9ea621637430d507723f2a1ad5766e7` |
| `IMP-MICROSOFT-SYNEOS-HEALTH-001` |  | 真相层 FDE-case-library/data/cases.json#microsoft-syneo | MIT（FDE-case-library） | 2026-11-12 | `5226c66f24d4bfbbbcd0adbd74be2ee7ff38c31b05b1a1d51c04b3898a0e022f` | `cc27287bb40e925ac9aab6a14f0c3821d1bc042d4c419ecc15cabc5573df713d` |
| `IMP-OPENAI-001` |  | 真相层 FDE-case-library/data/cases.json#openai-001（clon | MIT（FDE-case-library） | 2026-11-12 | `4dcc8588e000bf5bd4db2fdd7bc5123d89da4383544f00862652d573f9b92d63` | `5c13f5b6f130f6f329d21d011ff8e1fc2f0c5a54cab2a5471cb16eaef34e4633` |
| `IMP-OPENAI-002` |  | 真相层 FDE-case-library/data/cases.json#openai-002（clon | MIT（FDE-case-library） | 2026-11-12 | `597b3ba78cee74741718273b140f07e43ecea152667029c62a2100c5035c1ad1` | `e1d7662cb11bc1cf05808c84198568bc604f3740bdd1b3f0f4b745e7af1670e4` |
| `IMP-OPENAI-003` |  | 真相层 FDE-case-library/data/cases.json#openai-003（clon | MIT（FDE-case-library） | 2026-11-12 | `703faa4b45ab1ffb893cfefc1671aa29201b7a1638a54a3ef7009659f4aa44a0` | `7739916baf674e8bbcbaa2b886d5a0437587aba412e47c3694e2977585cdc2c9` |
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
| `IMP-OPENAI-017` |  | 真相层 FDE-case-library/data/cases.json#openai-017（clon | MIT（FDE-case-library） | 2026-11-12 | `0189847302cde9dc3c789a55544384449b01aa6b3ea7b72ab250a0b9d1f34f14` | `3e94d3c57799fad3d391e94f09dbd31925ac92fddd51907730f5ea39c27d8ccf` |
| `IMP-OPENAI-018` |  | 真相层 FDE-case-library/data/cases.json#openai-018（clon | MIT（FDE-case-library） | 2026-11-12 | `f04319da9d0746e6e0402e1db110f0fbc4d3af8810549ed7e85ad2ff39c913f8` | `af1be1176a2fa936dbf7acc08cd9fdc4d1c8f6f24b610a4c44b236b35c618da0` |
| `IMP-OPENAI-019` |  | 真相层 FDE-case-library/data/cases.json#openai-019（clon | MIT（FDE-case-library） | 2026-11-12 | `6e51cf197a46332750a09ee31e7881bd94c7d28fc781c9af6f3123387346afdc` | `a1e2e4fb63dd003e4b6040c426e34129a6f8415d4b8703c49812688a75c1a891` |
| `IMP-OPENAI-020` |  | 真相层 FDE-case-library/data/cases.json#openai-020（clon | MIT（FDE-case-library） | 2026-11-12 | `7990043d1d62d9110f57bc56e835ed3365eafd80fe064aa3c5d21ceabfa544a7` | `b96b811025242b611a0c1dbf4813de328f5d68970e55178789ae3e84be7c37f6` |
| `IMP-OPENAI-021` |  | 真相层 FDE-case-library/data/cases.json#openai-021（clon | MIT（FDE-case-library） | 2026-11-12 | `670aeb767f05aa51cdd6c5a5d29c997e037d577cf6cbebd52db1b1f48233fb8d` | `60478db078d0f2bcf8981b52715b212ed40b0b011e6e280161f536e4b70ec4e0` |
| `IMP-OPENAI-022` |  | 真相层 FDE-case-library/data/cases.json#openai-022（clon | MIT（FDE-case-library） | 2026-11-12 | `b4c27d01025eaa1cc1dc1892cd1cdf05bc85725c023371a1e80cf3485c731cf9` | `379c09f43b102823346eeddcd1baf8e4c2037aa9a9f8371a39bd80563fecea53` |
| `IMP-OPENAI-023` |  | 真相层 FDE-case-library/data/cases.json#openai-023（clon | MIT（FDE-case-library） | 2026-11-12 | `ed34bc7af37dbb7b002ac4a18c63f6e704ca1e0ebab4c7dce89118dcc01f9289` | `a2466b5d3de6b2a84891a330a0259120c958f32dc865647001c9051e7f2f1002` |
| `IMP-OPENAI-024` |  | 真相层 FDE-case-library/data/cases.json#openai-024（clon | MIT（FDE-case-library） | 2026-11-12 | `6ea3c7883f418d7f4cd288c8d8567a859d4c2160ca62a71ccd1dc34feaccbfbe` | `7dfb83cba66d51acb9bf27bd7bf3072f3893b03594b9f6458ee77abd526141a1` |
| `IMP-OPENAI-025` |  | 真相层 FDE-case-library/data/cases.json#openai-025（clon | MIT（FDE-case-library） | 2026-11-12 | `007c07cebe70a2fca94f58ef9b0c05a0edf93c1f7c88cc73928a535ae0d1c06f` | `52a6769ad85daa4292b64480cfb74819197c6d51c190fec975d6c42f5c178956` |
| `IMP-OPENAI-026` |  | 真相层 FDE-case-library/data/cases.json#openai-026（clon | MIT（FDE-case-library） | 2026-11-12 | `6eb1a5949b91db094509033c141919bedad97e6e4ded2713464e17daeb451bc0` | `77204af0d58c1d138c2f146fbf101b925e086e339861ac0a7d093fee8292c6a1` |
| `IMP-OPENAI-027` |  | 真相层 FDE-case-library/data/cases.json#openai-027（clon | MIT（FDE-case-library） | 2026-11-12 | `e48c126df9084773d47fd3912a5cfb760b5db8ad69a431160578ba985e278207` | `8a496853b43c080cecde1593a55126d1616c4c32bdecff129fd6121d4325df7e` |
| `IMP-OPENAI-028` |  | 真相层 FDE-case-library/data/cases.json#openai-028（clon | MIT（FDE-case-library） | 2026-11-12 | `aa2be8e772281169ea7985f2753f974d6cd7d1f7556b83da48ef91bf1e03ed78` | `e2b1fa547cd932b5c5930d017122a6939eb35ac8d47a70861c84230097142d7d` |
| `IMP-OPENAI-029` |  | 真相层 FDE-case-library/data/cases.json#openai-029（clon | MIT（FDE-case-library） | 2026-11-12 | `95e6613b00530cda6611c70a665e328ef4b53a54a96b93cdcafaf09e0d17fc82` | `7686d0429f5ec863cff3a5253052f585a17d6645b3a966bd45b0608c4fafddcb` |
| `IMP-OPENAI-030` |  | 真相层 FDE-case-library/data/cases.json#openai-030（clon | MIT（FDE-case-library） | 2026-11-12 | `8d9272d2a424111924d5a87d279bebcc1c8f7e60bd1932d6a72969883cae14b9` | `7d0e8e34911cb50e930ca90b4009890e17b2f165607efaf299cfbdf3dc8e6f4d` |
| `IMP-OPENAI-031` |  | 真相层 FDE-case-library/data/cases.json#openai-031（clon | MIT（FDE-case-library） | 2026-11-12 | `d75228b9d91d15f6c6ed7e56669a8a494f92c4f7930faced76a09d7f0cce0740` | `66d1aa35f96291780460594178efed34d8d21e4016a676f7af1a8e8b395acf4b` |
| `IMP-OPENAI-032` |  | 真相层 FDE-case-library/data/cases.json#openai-032（clon | MIT（FDE-case-library） | 2026-11-12 | `cae80d5acfcc7fa80eae7fd559010166f894f4fb6bc7b6cec03ef865a477553a` | `e0fbb9813b2ea084dc8a4b138aacf4995172f072676ba96f869397b7b4c4410d` |
| `IMP-OPENAI-033` |  | 真相层 FDE-case-library/data/cases.json#openai-033（clon | MIT（FDE-case-library） | 2026-11-12 | `d0fbd0d7a24524bbf0eed6852eb4538baa8d1204162258186d5a54427ae3b61a` | `615a4f0e88642c3ce397993d380ba0022693d8e87a02189b41d5c2637ec2b1b0` |
| `IMP-OPENAI-034` |  | 真相层 FDE-case-library/data/cases.json#openai-034（clon | MIT（FDE-case-library） | 2026-11-12 | `34a1d848f7cf01f9fc92c81be743f10a612378d2696428d9d395a10e2fda6388` | `9000b5d5d64ab04d8b88bf72cc3e1ddc4112b1dbf98de8e1a7b09f93979f5a9e` |
| `IMP-OPENAI-035` |  | 真相层 FDE-case-library/data/cases.json#openai-035（clon | MIT（FDE-case-library） | 2026-11-12 | `9dac213a0ace0c69a5b1d6dab1e4cd4933028fa21f2f543f7cac00c03bfda012` | `d04af0e492f5e2f3914b24f99d4d5b39cfab9fc78bf82208c664895e8d24fbb9` |
| `IMP-PALANTIR-001` |  | 真相层 FDE-case-library/data/cases.json#palantir-001（cl | MIT（FDE-case-library） | 2026-11-12 | `ab1e44a94a34b4e61126c80031725bed02ed63669830ab40cfdf1faf27bd83be` | `adabc791c3590dcfce516ee2866c1b018dffc29607ed643260b0afe675107bca` |
| `IMP-PALANTIR-002` |  | 真相层 FDE-case-library/data/cases.json#palantir-002（cl | MIT（FDE-case-library） | 2026-11-12 | `1090f987c9d1d5979b76d4dc0ef090a1f84783014d080f3f1aaf777bda877be2` | `249edae9c7e1047a4b046cad60c02470144054f92f92d78f8937f9fd70a5fa80` |
| `IMP-PALANTIR-003` |  | 真相层 FDE-case-library/data/cases.json#palantir-003（cl | MIT（FDE-case-library） | 2026-11-12 | `30ed16b30d23eaa23adc5f251940a5cb8789af65a90db9e3980d63e7f47c3278` | `4830c1f6916e434003d825445d445cfa167c03a2d40b81bb3edb635d26dab17e` |
| `IMP-PALANTIR-004` |  | 真相层 FDE-case-library/data/cases.json#palantir-004（cl | MIT（FDE-case-library） | 2026-11-12 | `b367c6a67cf3d7e2dee6180371c01c3365d38807fc26fb1875429e4edfed56ae` | `1f4f3dab2f35d87b1daff1902e377e380a5bc3b6c4b5e8663dffc98a77972eec` |
| `IMP-PALANTIR-005` |  | 真相层 FDE-case-library/data/cases.json#palantir-005（cl | MIT（FDE-case-library） | 2026-11-12 | `1bd268e37221bde03d9bc028d64a39d2275175f577b925633328f6b4d22a7e5e` | `df2477cba4080f61667b1d5fa96f507666f700ec096eded547c63b3fc84b71bd` |
| `IMP-PALANTIR-006` |  | 真相层 FDE-case-library/data/cases.json#palantir-006（cl | MIT（FDE-case-library） | 2026-11-12 | `5b670bea310ea6b449772b2038565875eff5cfd93892a34024cb083c2b6d6da0` | `de0c4a4014dc3e3e2a99b2f3e7537f4cb5b99f7b4fdd182837ee5cea7bfd4ec2` |
| `IMP-PALANTIR-007` |  | 真相层 FDE-case-library/data/cases.json#palantir-007（cl | MIT（FDE-case-library） | 2026-11-12 | `a9297af65843ea5e1b7b00ec51e2aad71f92e5644d8680fd0d1caf668806a6fb` | `888c9edb4a202c2f77c45bdd6a177dfc437a69e6a0553ab43f5cf9fb983874bf` |
| `IMP-PALANTIR-008` |  | 真相层 FDE-case-library/data/cases.json#palantir-008（cl | MIT（FDE-case-library） | 2026-11-12 | `2ec02adc0d81c3c0d37d5f6b14a893ef6fddf719e006d7a683f026682766b36a` | `80d294ceae573a62f9a3f12a921a3e7f7a4cffd2c8925e590c4f5c19fdff4129` |
| `IMP-PALANTIR-009` |  | 真相层 FDE-case-library/data/cases.json#palantir-009（cl | MIT（FDE-case-library） | 2026-11-12 | `6d9c1eb9191a90a7daa9612cf70e92ea0bfdfa725ac50c1c4d0a512b5ad17092` | `bf5a1ac8bf2f26a6b4e88a853e2ef270d09bb73cc2fd12ddabbc3de494a6bdd4` |
| `IMP-PALANTIR-010` |  | 真相层 FDE-case-library/data/cases.json#palantir-010（cl | MIT（FDE-case-library） | 2026-11-12 | `cc7f8d7bb766e0680bb30207a5492ee2ac50a882ba574598c1b703e14f1501bf` | `ef8cfcfe8d6fde9e1c50d72d52cf44aec2c804314c826b32c19c5b1dbbcd6784` |
| `IMP-PALANTIR-011` |  | 真相层 FDE-case-library/data/cases.json#palantir-011（cl | MIT（FDE-case-library） | 2026-11-12 | `cce69455e89004a5656a282fb6c4ab786d5e99b37f1208152e8846e095e48379` | `2e1025d21435c6874463df3fde54b63fa831bd6dbe7f8da9f067df6e1bb8ab7c` |
| `IMP-PALANTIR-012` |  | 真相层 FDE-case-library/data/cases.json#palantir-012（cl | MIT（FDE-case-library） | 2026-11-12 | `1f4c0550808d7e6b2bc6581e7db4d8fe6d128fdcd1d994788d20eed3bd870d2b` | `1778ed0a5090e5c0199310afe13d026ea48a6368bdb0ed688e613a3e319de9f9` |
| `IMP-PALANTIR-013` |  | 真相层 FDE-case-library/data/cases.json#palantir-013（cl | MIT（FDE-case-library） | 2026-11-12 | `0657bd3b77608363ca80e37f1b5e2daa40511e3fd0a2df920f6638cd84d43e34` | `ec0401fe07939be69ea184e32c0f411d471dd5bc147ae5d1248bf97946952efb` |
| `IMP-PALANTIR-014` |  | 真相层 FDE-case-library/data/cases.json#palantir-014（cl | MIT（FDE-case-library） | 2026-11-12 | `409b676ab5098d8c646da7a92aab32ac38a83eb6551e468e018568a2f078afe3` | `724f548b1b6529cd714c7d830926d350a9b2b3630b9a23d9f444fe985ff7eefe` |
| `IMP-PALANTIR-015` |  | 真相层 FDE-case-library/data/cases.json#palantir-015（cl | MIT（FDE-case-library） | 2026-11-12 | `8cdfd08846d3c593a168547d4524cb9ec65df1738c5c70dbbe8b1259549a1c33` | `80d059ebb51df1a9bacd286c2313583a5a2024fb133c858bbbf78567decd05d5` |
| `IMP-PALANTIR-016` |  | 真相层 FDE-case-library/data/cases.json#palantir-016（cl | MIT（FDE-case-library） | 2026-11-12 | `48021c189fd884175166b52851b1c814063c8e5d553c32073100f4182f76569f` | `cafabb9f1121b3d923976e04ca8cd5d757e8da66dae04f4ac0386c65c8d2033a` |
| `IMP-PALANTIR-017` |  | 真相层 FDE-case-library/data/cases.json#palantir-017（cl | MIT（FDE-case-library） | 2026-11-12 | `ffec3abe2bb93d0821fb93dcc5d59100f04db9cc446d57cefd1d3340fc5ce02a` | `9c8e93d887b283c83beccd046d7120a5990a7af186543740c9ab3a7f99552ee1` |
| `IMP-PALANTIR-018` |  | 真相层 FDE-case-library/data/cases.json#palantir-018（cl | MIT（FDE-case-library） | 2026-11-12 | `d9fd9901923ae729ebbccc921707a8ee3232dbfcca31b1a75aa765fdd90d8f40` | `4c26213120229897eb547cce196cd078ecd81f93223e328acf939b96edecaf7f` |
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

辅助件：合并批次件 packages\import-batch-20261112.json sha `46c6a292247973804f3412dbfe624aba5807e39aeaa64054a9f37df61610e029`；`manifest.json`（转换器生成，时间戳 2026-11-12T13:02:08.573745+00:00）。

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

## §5 验收记录（2026-11-12 现测）

- **四闸两轮独立实测全过**：①主会话本地跑转换器 134 包／失败 0；②工作流复核轮（同一转换器、独立执行）134/134 包通过、零发现——两轮结论一致。
- 装配器骨架装配：127/127（missing=0、invalid=0）；起草块形状零违规（94 例工作流产出＋33 例主会话补齐，同一键名契约）。
- 辅助件指纹：合并批次件 `import-batch-20261112.json` sha `46c6a292247973804f3412dbfe624aba5807e39aeaa64054a9f37df61610e029`；`manifest.json`（逐包指纹与时间戳，转换器生成）。
- 污染隔离：本轮零接触诊断评测答案（评测答案目录零触碰）；单向阀口径不变（判卷基准只进训练场 judge 面）。
- **未做（恒人工）**：draft 建行与激活——AI 不代发起、不碰 API；134 包全部 `variant='normal' / source_kind='import' / rubric_version='rubric-v1' / split='train'`，vague/complex 变体留训练场变异机制按需物化。
