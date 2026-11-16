国际人工智能公共服务容量预测与调度台

运行验收：
python3 -m public_ai_capacity run --fixture fixtures/acceptance.json --database /tmp/public_ai_capacity.sqlite3 --output /tmp/public_ai_capacity-output

核验：
python3 -m public_ai_capacity verify --database /tmp/public_ai_capacity.sqlite3 --output /tmp/public_ai_capacity-output

全量测试：
python3 -m unittest discover -s tests -v

按模块测试：
python3 -m unittest tests.capacity_signal.test_capacity_pressure -v

构建检查：
python3 -m compileall -q public_ai_capacity tests
