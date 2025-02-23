resource "aws_s3_bucket" "bronce" {
  bucket        = "my-bronce-bucket-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}
resource "aws_s3_bucket" "silver" {
  bucket        = "my-silver-bucket-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}
resource "aws_s3_bucket" "gold" {
  bucket        = "my-gold-bucket-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}
resource "aws_s3_bucket" "dependencies" {
  bucket        = "my-dependencies-bucket-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_object" "dependencies" {
  for_each    = fileset("./glueAssets/", "**")
  bucket      = aws_s3_bucket.dependencies.id
  key         = "glueAssets/${each.value}"
  source      = "./glueAssets/${each.value}"
  source_hash = filemd5("./glueAssets/${each.value}")
}
