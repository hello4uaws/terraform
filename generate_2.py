import os
import json
from jinja2 import Environment, FileSystemLoader

# Directories for templates and output files
TEMPLATE_DIR = "templates"
OUTPUT_DIR = "output"

def load_config(config_path="config_1.json"):
    """Loads JSON configuration"""
    with open(config_path) as f:
        return json.load(f)

def render_template(provider, resource_type, values):
    """Renders Jinja2 template for a given provider and resource type"""
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    try:
        template = env.get_template(f"{provider}/{resource_type}.j2")
    except FileNotFoundError:
        raise FileNotFoundError(f"Template not found: {provider}/{resource_type}.j2")
    return template.render(**values)

# ---------------- Provider Block Generators ----------------

def generate_provider_block_aws(region):
    """Generates Terraform provider block for AWS"""
    return f'''provider "aws" {{
  region     = "{region}"
  access_key = "{os.environ.get('AWS_ACCESS_KEY_ID', '')}"
  secret_key = "{os.environ.get('AWS_SECRET_ACCESS_KEY', '')}"
}}\n\n'''

def generate_provider_block_azure(region):
    """Generates Terraform provider block for Azure"""
    return f'''provider "azurerm" {{
  features {{}}
  subscription_id = "{os.environ.get('ARM_SUBSCRIPTION_ID', '')}"
  tenant_id       = "{os.environ.get('ARM_TENANT_ID', '')}"
  client_id       = "{os.environ.get('ARM_CLIENT_ID', '')}"
  client_secret   = "{os.environ.get('ARM_CLIENT_SECRET', '')}"
}}\n\n'''

def generate_provider_block_gcp(region):
    """Generates Terraform provider block for GCP"""
    return f'''provider "google" {{
  region  = "{region}"
  project = "{os.environ.get('GCP_PROJECT_ID', '')}"
  credentials = "{os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '')}"
}}\n\n'''

# ---------------- Resource Dependencies Management ----------------

def handle_aws_dependencies(resource, resource_refs):
    """Manages AWS resource dependencies"""
    resource_type = resource["type"]
    resource_name = resource.get("name", resource_type)

    # VPC dependencies
    if resource_type == "vpc":
        resource_refs["vpc"] = {
            "id": f"aws_vpc.{resource_name}.id",
            "cidr_block": f"aws_vpc.{resource_name}.cidr_block",
            "name": resource_name
        }
    # Subnet dependencies
    elif resource_type == "subnet":
        vpc_name = resource.get("vpc_name")
        if not vpc_name:
            raise ValueError(f"Subnet {resource_name} requires a vpc_name")
        resource["vpc_name"] = vpc_name  # Pass the VPC name to the template
        resource_refs["subnet"] = {
            "id": f"aws_subnet.{resource_name}.id",
            "arn": f"aws_subnet.{resource_name}.arn",
            "name": resource_name
        }
    # Security Group dependencies
    elif resource_type == "security_group":
        vpc_name = resource.get("vpc_name")
        if not vpc_name:
            raise ValueError(f"Security Group {resource_name} requires a vpc_name")
        resource["vpc_name"] = vpc_name  # Pass the VPC name to the template
        resource_refs["security_group"] = {
            "id": f"aws_security_group.{resource_name}.id",
            "name": resource_name
        }
    # EC2 Instance dependencies
    elif resource_type in ["instance", "ec2_instance"]:
        subnet_name = resource.get("subnet_name")
        sg_name = resource.get("security_group_name")
        if subnet_name:
            resource["subnet_id"] = f"aws_subnet.{subnet_name}.id"
        if sg_name:
            resource["vpc_security_group_ids"] = [f"aws_security_group.{sg_name}.id"]
    # RDS dependencies
    elif resource_type == "db_instance":
        subnet_name = resource.get("subnet_name")
        sg_name = resource.get("security_group_name")
        if subnet_name:
            resource["db_subnet_group_name"] = f"aws_subnet.{subnet_name}.id"
        if sg_name:
            resource["vpc_security_group_ids"] = [f"aws_security_group.{sg_name}.id"]

    return resource

def handle_gcp_dependencies(resource, resource_refs):
    """Manages GCP resource dependencies"""
    resource_type = resource["type"]
    resource_name = resource.get("name", resource_type)

    # VPC Network dependencies
    if resource_type == "compute_network":
        resource_refs["network"] = {
            "id": f"google_compute_network.{resource_name}.id",
            "name": f"google_compute_network.{resource_name}.name",
            "self_link": f"google_compute_network.{resource_name}.self_link"
        }
    # Subnet dependencies
    elif resource_type == "compute_subnetwork":
        network_ref = resource_refs.get("network", {})
        resource["network"] = network_ref.get("self_link", "")
        resource_refs["subnetwork"] = {
            "id": f"google_compute_subnetwork.{resource_name}.id",
            "self_link": f"google_compute_subnetwork.{resource_name}.self_link"
        }
    # Firewall dependencies
    elif resource_type == "compute_firewall":
        network_ref = resource_refs.get("network", {})
        resource["network"] = network_ref.get("self_link", "")
        resource_refs["firewall"] = {
            "id": f"google_compute_firewall.{resource_name}.id"
        }
    # Instance dependencies
    elif resource_type == "compute_instance":
        subnetwork_ref = resource_refs.get("subnetwork", {})
        if subnetwork_ref:
            resource["network_interface"] = [{
                "subnetwork": subnetwork_ref.get("self_link", "")
            }]
    # Cloud SQL dependencies
    elif resource_type == "sql_database_instance":
        network_ref = resource_refs.get("network", {})
        if network_ref:
            resource["private_network"] = network_ref.get("self_link", "")

    return resource

def handle_azure_dependencies(resource, resource_refs):
    """Manages Azure resource dependencies"""
    resource_type = resource["type"]
    resource_name = resource.get("name", resource_type)

    # Resource Group dependencies
    if "resource_group_name" in resource:
        rg_name = resource["resource_group_name"]
        resource["resource_group_name"] = f"azurerm_resource_group.{rg_name}.name"
        resource_refs["resource_group"] = rg_name

    # Network dependencies
    if resource_type == "virtual_network":
        resource_refs["vnet"] = {
            "name": resource_name,
            "id": f"azurerm_virtual_network.{resource_name}.id",
            "name_ref": f"azurerm_virtual_network.{resource_name}.name"
        }
    elif resource_type == "subnet":
        if "virtual_network_name" in resource:
            vnet_name = resource["virtual_network_name"]
            resource["virtual_network_name"] = f"azurerm_virtual_network.{vnet_name}.name"
        resource_refs["subnet"] = {
            "name": resource_name,
            "id": f"azurerm_subnet.{resource_name}.id"
        }
    elif resource_type == "network_interface":
        if "subnet_id" in resource:
            subnet_ref = resource_refs.get("subnet", {})
            resource["subnet_id"] = subnet_ref.get("id", "")
        resource_refs["nic"] = {
            "name": resource_name,
            "id": f"azurerm_network_interface.{resource_name}.id"
        }
    elif resource_type == "linux_virtual_machine":
        nic_ref = resource_refs.get("nic", {})
        resource["network_interface_ids"] = [nic_ref.get("id", "")]
    elif resource_type == "mysql_flexible_server":
        # Add any MySQL server specific dependencies
        pass
    elif resource_type == "storage_account":
        # Add any storage account specific dependencies
        pass

    return resource

# ---------------- Terraform File Generation ----------------

def generate_tf_files(config):
    """Generates Terraform files based on provider"""
    provider = config["provider"]
    region = config.get("region", "")
    
    # Select correct provider block function
    if provider == "aws":
        provider_block = generate_provider_block_aws(region)
    elif provider == "azurerm":
        provider_block = generate_provider_block_azure(region)
    elif provider == "google":
        provider_block = generate_provider_block_gcp(region)
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    full_output = provider_block
    resource_refs = {}
    resources = config["resources"]

    # First pass: Create base network resources
    for resource in resources:
        base_resources = {
            "aws": ["vpc", "subnet", "security_group"],
            "azurerm": ["resource_group", "virtual_network", "subnet"],
            "google": ["compute_network", "compute_subnetwork", "compute_firewall"]
        }
        if resource["type"] in base_resources.get(provider, []):
            if provider == "aws":
                resource = handle_aws_dependencies(resource, resource_refs)
            elif provider == "azurerm":
                resource = handle_azure_dependencies(resource, resource_refs)
            elif provider == "google":
                resource = handle_gcp_dependencies(resource, resource_refs)
            rendered = render_template(provider, resource["type"], resource)
            full_output += rendered + "\n\n"

    # Second pass: Create dependent resources
    for resource in resources:
        base_resources = {
            "aws": ["vpc", "subnet", "security_group"],
            "azurerm": ["resource_group", "virtual_network", "subnet"],
            "google": ["compute_network", "compute_subnetwork", "compute_firewall"]
        }
        if resource["type"] not in base_resources.get(provider, []):
            if provider == "aws":
                resource = handle_aws_dependencies(resource, resource_refs)
            elif provider == "azurerm":
                resource = handle_azure_dependencies(resource, resource_refs)
            elif provider == "google":
                resource = handle_gcp_dependencies(resource, resource_refs)
            rendered = render_template(provider, resource["type"], resource)
            full_output += rendered + "\n\n"

    # Save Terraform file
    out_dir = os.path.join(OUTPUT_DIR, provider)
    os.makedirs(out_dir, exist_ok=True)

    output_file = os.path.join(out_dir, "main.tf")
    with open(output_file, "w") as f:
        f.write(full_output)

    print(f"✅ Terraform file generated successfully: {output_file}")
    print(f"Resource dependencies tracked: {list(resource_refs.keys())}")

# ---------------- Execute Script ----------------

if __name__ == "__main__":
    config = load_config()
    generate_tf_files(config)
