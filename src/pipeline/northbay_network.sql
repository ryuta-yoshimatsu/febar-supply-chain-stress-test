-- Lakeflow Declarative Pipeline: NorthBay Foods supply network
-- Raw ERP / SRM / PLM / WMS / APS extracts (UC Volume) -> bronze -> silver (quality rules) -> gold (network model)
-- ${raw_root} is set in the pipeline configuration, e.g. /Volumes/<catalog>/<schema>/raw_landing

------------------------------------------------------------------------------------------
-- Bronze: incremental ingestion with Auto Loader (read_files), schema inferred, source file kept
------------------------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE bronze_products
COMMENT 'Raw ERP product & plant master extracts'
AS SELECT *, _metadata.file_path AS source_file, current_timestamp() AS ingested_at
FROM STREAM read_files('${raw_root}/erp/products', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_suppliers
COMMENT 'Raw SRM supplier master extracts'
AS SELECT *, _metadata.file_path AS source_file, current_timestamp() AS ingested_at
FROM STREAM read_files('${raw_root}/srm/suppliers', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_materials
COMMENT 'Raw SRM material master'
AS SELECT *, _metadata.file_path AS source_file, current_timestamp() AS ingested_at
FROM STREAM read_files('${raw_root}/srm/materials', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_supply_links
COMMENT 'Raw PLM approved supplier-to-customer links (JSON lines)'
AS SELECT *, _metadata.file_path AS source_file, current_timestamp() AS ingested_at
FROM STREAM read_files('${raw_root}/plm/supply_links', format => 'json');

CREATE OR REFRESH STREAMING TABLE bronze_inventory
COMMENT 'Raw WMS weekly on-hand inventory snapshots (JSON lines)'
AS SELECT *, _metadata.file_path AS source_file, current_timestamp() AS ingested_at
FROM STREAM read_files('${raw_root}/wms/inventory', format => 'json');

CREATE OR REFRESH STREAMING TABLE bronze_demand_forecast
COMMENT 'Raw APS 13-week demand forecast'
AS SELECT *, _metadata.file_path AS source_file, current_timestamp() AS ingested_at
FROM STREAM read_files('${raw_root}/aps/demand_forecast', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_scenarios
COMMENT 'Raw named disruption scenarios curated by the supply chain risk team'
AS SELECT *, _metadata.file_path AS source_file, current_timestamp() AS ingested_at
FROM STREAM read_files('${raw_root}/risk/scenarios', format => 'csv', header => true);

------------------------------------------------------------------------------------------
-- Silver: typed, deduplicated, validated
------------------------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW silver_products (
  CONSTRAINT valid_product_id EXPECT (product_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT positive_margin EXPECT (margin_usd_per_case > 0) ON VIOLATION DROP ROW,
  CONSTRAINT positive_capacity EXPECT (capacity_cases_per_week > 0) ON VIOLATION DROP ROW
)
COMMENT 'Finished-goods plants (Tier 1), latest record per product'
AS SELECT product_id, product_name, brand, category, plant_name, plant_city, plant_state,
          CAST(capacity_cases_per_week AS INT) AS capacity_cases_per_week,
          CAST(margin_usd_per_case AS DOUBLE) AS margin_usd_per_case,
          CAST(price_usd_per_case AS DOUBLE) AS price_usd_per_case,
          CAST(updated_at AS DATE) AS updated_at
FROM bronze_products
QUALIFY row_number() OVER (PARTITION BY product_id ORDER BY updated_at DESC, ingested_at DESC) = 1;

CREATE OR REFRESH MATERIALIZED VIEW silver_suppliers (
  CONSTRAINT valid_supplier_id EXPECT (supplier_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT valid_tier EXPECT (tier IN (2, 3)) ON VIOLATION DROP ROW,
  CONSTRAINT positive_capacity EXPECT (capacity_units_per_week > 0) ON VIOLATION DROP ROW,
  CONSTRAINT valid_recovery EXPECT (expected_recovery_weeks BETWEEN 1 AND 52)
)
COMMENT 'Tier-2 co-packers / converters and Tier-3 raw material suppliers, deduplicated'
AS SELECT supplier_id, supplier_name, CAST(tier AS INT) AS tier, material_id, city, region,
          CAST(capacity_units_per_week AS INT) AS capacity_units_per_week,
          CAST(expected_recovery_weeks AS INT) AS expected_recovery_weeks,
          disruption_profile, CAST(updated_at AS DATE) AS updated_at
FROM bronze_suppliers
QUALIFY row_number() OVER (PARTITION BY supplier_id ORDER BY updated_at DESC, ingested_at DESC) = 1;

CREATE OR REFRESH MATERIALIZED VIEW silver_materials
COMMENT 'Material master'
AS SELECT DISTINCT material_id, material_name, CAST(tier AS INT) AS tier, unit FROM bronze_materials;

CREATE OR REFRESH MATERIALIZED VIEW silver_supply_links (
  CONSTRAINT known_source EXPECT (source_known) ON VIOLATION DROP ROW,
  CONSTRAINT known_target EXPECT (target_known) ON VIOLATION DROP ROW
)
COMMENT 'Approved supply links whose source and target exist in the masters'
AS WITH nodes AS (
  SELECT product_id AS node_id FROM silver_products
  UNION ALL SELECT supplier_id FROM silver_suppliers
)
SELECT DISTINCT l.source_id, l.target_id, l.material_id,
       s.node_id IS NOT NULL AS source_known,
       t.node_id IS NOT NULL AS target_known
FROM bronze_supply_links l
LEFT JOIN nodes s ON s.node_id = l.source_id
LEFT JOIN nodes t ON t.node_id = l.target_id
WHERE l.approved;

CREATE OR REFRESH MATERIALIZED VIEW silver_inventory (
  CONSTRAINT non_negative_on_hand EXPECT (on_hand_units >= 0) ON VIOLATION DROP ROW
)
COMMENT 'Weekly on-hand inventory per node'
AS SELECT node_id, CAST(snapshot_date AS DATE) AS snapshot_date, CAST(on_hand_units AS BIGINT) AS on_hand_units
FROM bronze_inventory;

CREATE OR REFRESH MATERIALIZED VIEW silver_demand_forecast (
  CONSTRAINT non_negative_forecast EXPECT (forecast_cases >= 0) ON VIOLATION DROP ROW
)
COMMENT 'Weekly demand forecast per product'
AS SELECT product_id, CAST(week_start AS DATE) AS week_start, CAST(forecast_cases AS INT) AS forecast_cases
FROM bronze_demand_forecast;

------------------------------------------------------------------------------------------
-- Gold: the network model consumed by the optimizer, Genie, Lakebase and the app
------------------------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW gold_network_nodes
COMMENT 'One row per network node (plant or supplier) with the parameters of the stress-test model: weekly capacity, latest on-hand inventory, next-4-week average demand and unit margin (finished goods only)'
AS WITH latest_inv AS (
  SELECT node_id, on_hand_units, snapshot_date
  FROM silver_inventory
  QUALIFY row_number() OVER (PARTITION BY node_id ORDER BY snapshot_date DESC) = 1
), demand AS (
  SELECT product_id, avg(forecast_cases) AS demand_per_week
  FROM (SELECT *, row_number() OVER (PARTITION BY product_id ORDER BY week_start) AS wk FROM silver_demand_forecast)
  WHERE wk <= 4
  GROUP BY product_id
)
SELECT p.product_id AS node_id, p.product_name AS node_name, 1 AS tier, 'Finished-goods plant' AS node_type,
       CAST(NULL AS STRING) AS material_id, CAST(NULL AS STRING) AS material_name,
       p.plant_name AS site_name, p.plant_city AS city, p.plant_state AS region,
       p.capacity_cases_per_week AS capacity_per_week, i.on_hand_units, i.snapshot_date AS inventory_as_of,
       d.demand_per_week, p.margin_usd_per_case AS margin_usd_per_unit, p.price_usd_per_case AS price_usd_per_unit,
       CAST(NULL AS INT) AS expected_recovery_weeks, CAST(NULL AS STRING) AS disruption_profile,
       p.brand, p.category
FROM silver_products p
LEFT JOIN latest_inv i ON i.node_id = p.product_id
LEFT JOIN demand d ON d.product_id = p.product_id
UNION ALL
SELECT s.supplier_id, s.supplier_name, s.tier,
       CASE s.tier WHEN 2 THEN 'Tier-2 co-packer / converter' ELSE 'Tier-3 raw material supplier' END,
       s.material_id, m.material_name, s.supplier_name, s.city, s.region,
       s.capacity_units_per_week, i.on_hand_units, i.snapshot_date,
       0.0, 0.0, 0.0, s.expected_recovery_weeks, s.disruption_profile, CAST(NULL AS STRING), CAST(NULL AS STRING)
FROM silver_suppliers s
LEFT JOIN silver_materials m ON m.material_id = s.material_id
LEFT JOIN latest_inv i ON i.node_id = s.supplier_id;

CREATE OR REFRESH MATERIALIZED VIEW gold_supply_links
COMMENT 'Directed supply links (source supplies material_id to target)'
AS SELECT concat(source_id, '->', target_id) AS link_id, source_id, target_id, material_id
FROM silver_supply_links;

CREATE OR REFRESH MATERIALIZED VIEW gold_sourcing_exposure
COMMENT 'Number of approved suppliers per (customer node, material); n_suppliers = 1 means a single point of failure'
AS SELECT concat(l.target_id, '|', l.material_id) AS exposure_id, l.target_id AS node_id, t.node_name,
          l.material_id, m.material_name, count(*) AS n_suppliers,
          array_join(sort_array(collect_list(l.source_id)), ', ') AS supplier_ids,
          count(*) = 1 AS single_sourced
FROM gold_supply_links l
JOIN gold_network_nodes t ON t.node_id = l.target_id
LEFT JOIN silver_materials m ON m.material_id = l.material_id
GROUP BY l.target_id, t.node_name, l.material_id, m.material_name;

CREATE OR REFRESH MATERIALIZED VIEW gold_disruption_scenarios
COMMENT 'Named multi-node disruption scenarios'
AS SELECT DISTINCT scenario_id, scenario_name, split(disrupted_node_ids, ';') AS disrupted_node_ids,
          CAST(recovery_weeks AS INT) AS recovery_weeks
FROM bronze_scenarios;
