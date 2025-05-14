import os
import re
import glob
from typing import List, Dict, Any
import warnings
from pydantic import BaseModel, Field
from crewai import Agent, Task, Crew
from langchain_openai import AzureChatOpenAI  # Import Azure OpenAI integration

# Suppress warnings
warnings.filterwarnings('ignore')

class TerraformResource(BaseModel):
    """Pydantic model for Terraform resource information"""
    resource_type: str = Field(description="Type of the Terraform resource")
    resource_name: str = Field(description="Name of the Terraform resource")
    resource_id: str = Field(description="Full resource identifier (type.name)")
    file_path: str = Field(description="Path to the file containing this resource")
    is_module: bool = Field(description="Whether this is a module or a resource", default=False)
    module_source: str = Field(description="Source of the module if this is a module", default=None)

class TerraformProjectResources(BaseModel):
    """Pydantic model for the output containing all resources in a Terraform project"""
    resources: List[TerraformResource] = Field(description="List of all resources found in the project")
    resource_count: int = Field(description="Total number of resources found")
    resource_types: Dict[str, int] = Field(description="Count of resources by type")

class TerraformParser:
    """Helper class to parse Terraform files and extract resources"""

    @staticmethod
    def parse_terraform_file(file_path: str) -> List[TerraformResource]:
        """Parse a single Terraform file and extract resources and modules"""
        resources = []

        try:
            with open(file_path, 'r') as f:
                content = f.read()

            # Regular expression to find resource declarations
            # Format: resource "type" "name" { ... }
            resource_pattern = r'resource\s+"([^"]+)"\s+"([^"]+)"'
            resource_matches = re.finditer(resource_pattern, content)

            for match in resource_matches:
                resource_type = match.group(1)
                resource_name = match.group(2)
                resource_id = f"{resource_type}.{resource_name}"

                resources.append(TerraformResource(
                    resource_type=resource_type,
                    resource_name=resource_name,
                    resource_id=resource_id,
                    file_path=file_path,
                    is_module=False
                ))

            # Regular expression to find module declarations and their sources
            # Format: module "name" { source = "source/path" ... }
            module_pattern = r'module\s+"([^"]+)"\s+{[^}]*source\s+=\s+"([^"]+)"'
            module_matches = re.finditer(module_pattern, content)

            for match in module_matches:
                module_name = match.group(1)
                module_source = match.group(2)

                # Extract the last part of the module source path
                # E.g., "tfe.mycompany.com/MODULE-REGISTRY/rds-aurora-postgres/aws" -> "rds-aurora-postgres"
                source_parts = module_source.split('/')
                module_type = source_parts[-2] if len(source_parts) >= 2 else module_source

                resources.append(TerraformResource(
                    resource_type=module_type,  # Use the extracted module type
                    resource_name=module_name,
                    resource_id=f"module.{module_name}",
                    file_path=file_path,
                    is_module=True,
                    module_source=module_source
                ))

        except Exception as e:
            print(f"Error parsing file {file_path}: {str(e)}")

        return resources

# Configure Azure OpenAI
def get_azure_openai_llm(
        deployment_name: str = None,
        model_name: str = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
):
    """
    Create and configure an Azure OpenAI language model

    Args:
        deployment_name: Azure deployment name
        model_name: Model name (e.g., 'gpt-4', 'gpt-35-turbo')
        temperature: Sampling temperature (0.0 to 1.0)
        max_tokens: Maximum tokens in completion

    Returns:
        Configured AzureChatOpenAI instance
    """
    # Get Azure OpenAI configuration from environment variables
    azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    azure_api_key = os.environ.get("AZURE_OPENAI_API_KEY")

    if not deployment_name:
        deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")

    if not model_name:
        model_name = os.environ.get("AZURE_OPENAI_MODEL_NAME", "gpt-4")

    # Create and return the LLM
    return AzureChatOpenAI(
        azure_deployment=deployment_name,
        openai_api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2023-05-15"),
        openai_api_key=azure_api_key,
        azure_endpoint=azure_endpoint,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens
    )

# Create our CrewAI Agent with Azure OpenAI
def analyze_terraform_project(
        terraform_directory: str,
        deployment_name: str = None,
        model_name: str = None
) -> List[str]:
    """
    Analyze a Terraform project directory and return a list of resource and module names

    Args:
        terraform_directory: Path to the Terraform project
        deployment_name: Azure deployment name
        model_name: Model name to use

    Returns:
        List of resource types found in the project
    """
    # Get the Azure OpenAI LLM
    azure_llm = get_azure_openai_llm(
        deployment_name=deployment_name,
        model_name=model_name
    )

    # Create the agent with the Azure OpenAI LLM
    terraform_analyzer = Agent(
        role="Terraform Project Analyzer",
        goal="Extract and analyze all resources from Terraform configuration files",
        verbose=True,
        backstory=(
            "As an expert in infrastructure as code, you specialize in analyzing "
            "Terraform projects to extract resource information, identify patterns, "
            "and provide insights about the infrastructure being defined."
        ),
        llm=azure_llm  # Use the Azure OpenAI LLM
    )

    # Task for extracting Terraform resources
    extract_resources_task = Task(
        description=f"Analyze all Terraform files in the directory '{terraform_directory}' and extract a list of all resources and modules defined",
        expected_output="A complete list of all Terraform resources and modules in the project",
        agent=terraform_analyzer,
        output_json=TerraformProjectResources
    )

    # Create the crew with the single agent and task
    terraform_analysis_crew = Crew(
        agents=[terraform_analyzer],
        tasks=[extract_resources_task],
        verbose=True
    )

    # This is the actual implementation of the resource extraction
    # (We're not really using the crew's execution for this since it's a straightforward task)
    all_resources = []
    terraform_files = []

    # Find all .tf files in the directory and its subdirectories
    for extension in ['*.tf', '*.tf.json']:
        terraform_files.extend(glob.glob(os.path.join(terraform_directory, "**", extension), recursive=True))

    # Parse each file to extract resources
    for tf_file in terraform_files:
        resources = TerraformParser.parse_terraform_file(tf_file)
        all_resources.extend(resources)

    # Create statistics for resource types
    resource_types = {}
    for resource in all_resources:
        if resource.resource_type in resource_types:
            resource_types[resource.resource_type] += 1
        else:
            resource_types[resource.resource_type] = 1

    # Create the final result object
    project_resources = TerraformProjectResources(
        resources=all_resources,
        resource_count=len(all_resources),
        resource_types=resource_types
    )

    # Return just the resource types as a list of strings
    # Use a set to remove duplicates, then convert back to list
    return list(set(resource.resource_type for resource in project_resources.resources))

# Usage example
if __name__ == "__main__":
    import sys
    import argparse

    # Create argument parser
    parser = argparse.ArgumentParser(description="Analyze Terraform projects using Azure OpenAI")
    parser.add_argument("--dir", "-d", help="Path to the Terraform project directory")
    parser.add_argument("--deployment", help="Azure OpenAI deployment name")
    parser.add_argument("--model", help="Azure OpenAI model name")

    args = parser.parse_args()

    terraform_dir = args.dir
    if not terraform_dir:
        terraform_dir = input("Enter the path to the Terraform project directory: ")

    # Run the analysis
    resource_list = analyze_terraform_project(
        terraform_directory=terraform_dir,
        deployment_name=args.deployment,
        model_name=args.model
    )

    print("\nResource types found in the Terraform project:")
    for idx, resource in enumerate(resource_list, 1):
        print(f"{idx}. {resource}")

    print(f"\nTotal unique resource types found: {len(resource_list)}")