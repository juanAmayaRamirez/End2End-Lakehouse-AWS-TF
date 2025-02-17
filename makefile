.PHONY: validate init plan apply show graph destroy

# default command when make is ran
.DEFAULT_GOAL := validate
ALLOWED_ENVS := dev qa demo prod


validate:
	terraform fmt
	terraform validate


init:
# Require S3BUCKET and WORKSPACE variables to be set
ifndef S3BUCKET
	$(error S3BUCKET is not set. Please specify an S3 bucket name, e.g., 'make init S3BUCKET=my-tf-state-bucket ENV=dev')
endif
ifndef ENV
	$(error ENV is not set. Please specify a environment name, e.g., 'make init S3BUCKET=my-tf-state-bucket ENV=dev')
endif
ifeq ($(filter $(ENV),$(ALLOWED_ENVS)),)
	$(error ENV must be one of the following values: $(ALLOWED_ENVS))
endif
	terraform init -reconfigure -backend-config="bucket=${S3BUCKET}" -backend-config="key=terraform-${ENV}/terraform.tfstate" -backend-config="region=us-east-1" 


plan:
ifndef ENV
	$(error ENV is not set. Please specify a environment name, e.g., 'make plan ENV=dev')
endif
ifeq ($(filter $(ENV),$(ALLOWED_ENVS)),)
	$(error ENV must be one of the following values: $(ALLOWED_ENVS))
endif
	terraform plan -var-file=variables/${ENV}.tfvars -var "env_name=${ENV}" -out=tfplan 


apply:
	terraform apply tfplan


show:
	terraform show


graph:
	terraform graph -type=plan | dot -Tsvg > .files/graph.svg


destroy:
ifndef ENV
	$(error ENV is not set. Please specify a environment name, e.g., 'make destroy ENV=dev')
endif
ifeq ($(filter $(ENV),$(ALLOWED_ENVS)),)
	$(error ENV must be one of the following values: $(ALLOWED_ENVS))
endif
	terraform destroy -var-file=variables/${ENV}.tfvars -var "env_name=${ENV}"