
resource "aws_glue_catalog_database" "lakehouse_db" {
  name = "lakehouse_db"
  # depends_on = [
  #   aws_lakeformation_data_lake_settings.access
  # ]
}