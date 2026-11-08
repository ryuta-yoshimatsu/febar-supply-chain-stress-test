# Execution evidence: Lakeflow data quality and Unity Catalog lineage

Captured 2026-11-08 09:36 UTC from workspace `adb-7405610715852579` (Azure) with the Statement Execution API on the Serverless Starter Warehouse.

## 1. Lakeflow pipeline expectations (latest update of `northbay-network-pipeline`)

The synthetic extracts contain three injected defects: a duplicated supplier record (removed by the silver dedup), a negative inventory scan (`non_negative_on_hand` → 1 row dropped) and a supply link to supplier `S299`, which does not exist in SRM (`known_source` → 1 row dropped).

```sql
WITH latest AS (SELECT origin.update_id AS u FROM event_log('ae6463f9-45ee-47d6-b872-ced8a89b8186') WHERE event_type = 'create_update' ORDER BY timestamp DESC LIMIT 1)
SELECT split(origin.flow_name, '\\.')[2] AS dataset, e.name AS expectation, sum(e.passed_records) AS passed, sum(e.failed_records) AS failed
FROM event_log('ae6463f9-45ee-47d6-b872-ced8a89b8186'),
     LATERAL explode(from_json(details:flow_progress.data_quality.expectations, 'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>')) AS t(e)
WHERE event_type = 'flow_progress' AND origin.update_id = (SELECT u FROM latest) AND details:flow_progress.data_quality IS NOT NULL
GROUP BY 1, 2 ORDER BY 1, 2
```

| dataset | expectation | passed | failed |
|---|---|---:|---:|
| silver_demand_forecast | non_negative_forecast | 65 | 0 |
| silver_inventory | non_negative_on_hand | 116 | 1 |
| silver_products | positive_capacity | 5 | 0 |
| silver_products | positive_margin | 5 | 0 |
| silver_products | valid_product_id | 5 | 0 |
| silver_suppliers | positive_capacity | 24 | 0 |
| silver_suppliers | valid_recovery | 24 | 0 |
| silver_suppliers | valid_supplier_id | 24 | 0 |
| silver_suppliers | valid_tier | 24 | 0 |
| silver_supply_links | known_source | 35 | 1 |
| silver_supply_links | known_target | 36 | 0 |

## 2. Unity Catalog lineage (`system.access.table_lineage`)

Raw Volume files → bronze → silver → gold (pipeline) → stress-test outputs (job) → Lakebase synced tables (`northbay_serving.*`).

```sql
SELECT DISTINCT coalesce(source_table_full_name, source_path, '(raw files / pandas)') AS source, target_table_full_name AS target, entity_type FROM system.access.table_lineage WHERE (target_table_full_name LIKE 'classic_stable_z57t9z_catalog.febar_supply_chain.%' OR target_table_full_name LIKE 'classic_stable_z57t9z_catalog.northbay_serving.%') AND target_table_full_name NOT LIKE '%event_log%' AND target_table_full_name NOT LIKE '%__materialization%' AND event_date >= current_date() - 3 ORDER BY target, source
```

| source | target | written by |
|---|---|---|
| (raw files / pandas) | febar_supply_chain.bronze_demand_forecast | PIPELINE |
| (raw files / pandas) | febar_supply_chain.bronze_inventory | PIPELINE |
| (raw files / pandas) | febar_supply_chain.bronze_materials | PIPELINE |
| (raw files / pandas) | febar_supply_chain.bronze_products | PIPELINE |
| (raw files / pandas) | febar_supply_chain.bronze_scenarios | PIPELINE |
| (raw files / pandas) | febar_supply_chain.bronze_suppliers | PIPELINE |
| (raw files / pandas) | febar_supply_chain.bronze_supply_links | PIPELINE |
| febar_supply_chain.bronze_scenarios | febar_supply_chain.gold_disruption_scenarios | PIPELINE |
| febar_supply_chain.silver_demand_forecast | febar_supply_chain.gold_network_nodes | PIPELINE |
| febar_supply_chain.silver_inventory | febar_supply_chain.gold_network_nodes | PIPELINE |
| febar_supply_chain.silver_materials | febar_supply_chain.gold_network_nodes | PIPELINE |
| febar_supply_chain.silver_products | febar_supply_chain.gold_network_nodes | PIPELINE |
| febar_supply_chain.silver_suppliers | febar_supply_chain.gold_network_nodes | PIPELINE |
| (raw files / pandas) | febar_supply_chain.gold_product_impact | JOB |
| febar_supply_chain.gold_network_nodes | febar_supply_chain.gold_sourcing_exposure | PIPELINE |
| febar_supply_chain.gold_supply_links | febar_supply_chain.gold_sourcing_exposure | PIPELINE |
| febar_supply_chain.silver_materials | febar_supply_chain.gold_sourcing_exposure | PIPELINE |
| (raw files / pandas) | febar_supply_chain.gold_stress_test_results | JOB |
| febar_supply_chain.silver_supply_links | febar_supply_chain.gold_supply_links | PIPELINE |
| febar_supply_chain.bronze_demand_forecast | febar_supply_chain.silver_demand_forecast | PIPELINE |
| febar_supply_chain.bronze_inventory | febar_supply_chain.silver_inventory | PIPELINE |
| febar_supply_chain.bronze_materials | febar_supply_chain.silver_materials | PIPELINE |
| febar_supply_chain.bronze_products | febar_supply_chain.silver_products | PIPELINE |
| febar_supply_chain.bronze_suppliers | febar_supply_chain.silver_suppliers | PIPELINE |
| febar_supply_chain.bronze_supply_links | febar_supply_chain.silver_supply_links | PIPELINE |
| febar_supply_chain.silver_products | febar_supply_chain.silver_supply_links | PIPELINE |
| febar_supply_chain.silver_suppliers | febar_supply_chain.silver_supply_links | PIPELINE |
| febar_supply_chain.gold_network_nodes | northbay_serving.network_nodes | PIPELINE |
| febar_supply_chain.gold_product_impact | northbay_serving.product_impact | PIPELINE |
| febar_supply_chain.gold_sourcing_exposure | northbay_serving.sourcing_exposure | PIPELINE |
| febar_supply_chain.gold_stress_test_results | northbay_serving.stress_test_results | PIPELINE |
| febar_supply_chain.gold_supply_links | northbay_serving.supply_links | PIPELINE |
