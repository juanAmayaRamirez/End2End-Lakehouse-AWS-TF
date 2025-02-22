data "template_file" "monitoring_notifications_policy" {
  template = file("./policies/sns_monitoring_policy.json")
  vars = {
    aws_account_id  = data.aws_caller_identity.current.account_id
  }
}
resource "aws_sns_topic" "monitoring_notifications" {
  name                        = "monitoring-sns-tpc"
  fifo_topic                  = false
  content_based_deduplication = false
  policy                      = data.template_file.monitoring_notifications_policy.rendered
  delivery_policy             = <<EOF
{
  "http": {
    "defaultHealthyRetryPolicy": {
      "minDelayTarget": 20,
      "maxDelayTarget": 20,
      "numRetries": 3,
      "numMaxDelayRetries": 0,
      "numNoDelayRetries": 0,
      "numMinDelayRetries": 0,
      "backoffFunction": "linear"
    },
    "disableSubscriptionOverrides": false,
    "defaultThrottlePolicy": {
      "maxReceivesPerSecond": 1
    }
  }
}
EOF

}

resource "aws_sns_topic_subscription" "sns_topic_subscription_sqs" {
  for_each  = var.monitoring_emails ? 1 : 0
  topic_arn = aws_sns_topic.monitoring_notifications.arn
  endpoint  = each.value
  protocol  = "email"
}