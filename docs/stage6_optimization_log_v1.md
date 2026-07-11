# Stage 6 Optimization Log v1

이 문서는 Stage 6 count export 속도 개선 실험을 한 곳에 모아 기록한다.

범위는 성능 최적화뿐이다. extraction rule, canonicalization rule, semantic repair rule은 추가하지 않는다.

## 고정 조건

- input: `outputs/benchmark_real10k_train/sentence_rows_9896.jsonl.gz`
- sentence count: 9,896
- model: `en_core_web_trf`
- batch size: 128
- length bucket size: 65536
- raw extraction mode: `doc-direct`
- object MWE lexicon size: 0
- GPU mode: `require-gpu`
- GPU: NVIDIA GeForce RTX 5080 Laptop GPU

## Baseline

초기 Stage 6는 약 18.0초 수준이었다.

Stage 6의 주된 비용은 `object_pair_in_caption` fact가 10k 기준 1,303,858개 생성되는 데서 나왔다.

## opt1: object pair metadata precompute

상태: 유지

변경:

- caption 내부 object별 `mention_ids_by_object`를 한 번만 만든다.
- caption 내부 object별 `rule_ids_by_object`를 한 번만 만든다.
- object pair마다 mention id와 rule id를 다시 계산하지 않는다.

이유:

- object pair는 같은 caption 안 object 조합을 순회하므로, object별 metadata가 반복 재계산되고 있었다.

결과:

- Stage 6 약 15.5초.

## opt2: count table aggregate one-pass experiment

상태: 폐기

변경:

- count table별로 `_aggregate_facts()`를 여러 번 호출하는 대신, 여러 table bucket을 한 번에 만들려고 했다.

결과:

- Stage 6 약 16.2초.
- opt1보다 느려서 revert했다.

판단:

- 코드 복잡도는 늘었지만 실제 병목을 줄이지 못했다.

## opt3: aggregate bucket direct accumulator experiment

상태: 폐기

변경:

- `_aggregate_facts()`에서 `FactRow` 리스트를 bucket에 쌓은 뒤 다시 세는 대신, count와 caption ids 등을 직접 누적하려고 했다.

결과:

- Stage 6 약 17.9초.
- opt1보다 느려서 revert했다.

판단:

- Python dict/set 조작 비용이 줄지 않았고, 구조만 복잡해졌다.

## opt4: Stage 6 internal FactRow fast construction

상태: 유지

변경:

- Stage 6 내부에서 생성하는 fact에 한해 `_make_fact_row()`를 사용한다.
- `FactRow.__post_init__()` 검증을 전역으로 끄지 않고, Stage 6에서 이미 검증된 canonical mention/edge와 내부 상수로 만드는 row에만 fast construction을 적용한다.

이유:

- cProfile에서 `FactRow.__post_init__()`와 내부 string/list validation 비용이 크게 잡혔다.
- Stage 6 생성 값은 canonical records와 고정 rule id에서 온다.

결과:

- `outputs/benchmark_stage6_opt4/summary_batch128_bucket65536_stage6_opt4.json`
- Stage 6 약 12.39초.
- fact/table counts unchanged.

검증:

- `python -m unittest tests.test_stage6_export_counts`
- `python -m unittest discover -s tests`

## opt5: object pair direct count row experiment

상태: 폐기

변경:

- `_object_pair_facts()`가 fact뿐 아니라 `object_cooccurrence_pair_counts.tsv`용 count row도 같이 만들도록 시도했다.
- 목적은 object pair fact를 만든 뒤 `_aggregate_facts()`로 다시 훑는 비용을 줄이는 것이었다.

결과:

- `outputs/benchmark_stage6_opt5/summary_batch128_bucket65536_stage6_opt5.json`
- Stage 6 약 13.60초.
- opt4보다 느려서 revert했다.

판단:

- 직접 count row를 만들기 위한 caption id, rule id 누적 비용이 이득보다 컸다.
- 현재 코드에는 opt5가 남아 있지 않다.

## 현재 채택 상태

현재 유지하는 최적화는 opt1과 opt4뿐이다.

현재 benchmark:

- `outputs/benchmark_stage6_current/summary_batch128_bucket65536_current.json`
- Stage 6: 약 12.61초
- processing speed: 약 172 captions/sec
- total speed: 약 168 captions/sec

## 다음 판단

Stage 6 micro-optimization은 현재 수익이 줄어든 상태다.

다음 우선순위는 100k 또는 1M scale benchmark에서 병목 분포가 10k와 같은지 확인하는 것이다.
