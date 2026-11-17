# pairwise-save-migrate

老存档迁移现在只改版本号，v1 的 `coins` 字段没有搬进 `wallet`，新版本上线后老存档读进游戏武器等级全是 0；云存档校验和 `checksum` 忽略排序，玩家回档后看起来一样但 inventory 已经换了位置；云同步 `merge_cloud` 直接用远端覆盖本地，进度低的设备把高进度冲掉；迁移失败没有回滚，坏档直接写回；缺失字段没有默认值，读档时 KeyError。save/migrate.py 是核心，tests/test_migrate.py 15个红。要修的是：按版本链逐级迁移并处理字段重命名/默认值；inventory 按 id 建索引；checksum 对嵌套字段和顺序敏感；云同步按进度/版本取高；目标版本低于源版本报错；迁移幂等且不修改原对象。

## 运行

```bash
python -m pytest tests -q
```

初始状态：15 个用例失败。修复实现使全部用例通过，不要修改 `tests/` 下的测试。
