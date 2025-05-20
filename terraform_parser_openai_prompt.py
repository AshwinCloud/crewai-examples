import os
import glob
from pathlib import Path
from typing import List, Optional
import argparse
from pydantic import BaseModel, Field
from openai import OpenAI

from dotenv import load_dotenv, find_dotenv

# these expect to find a .env file at the directory above the lesson.                                                                                                                     # the format for that file is (without the comment)                                                                                                                                       #API_KEYNAME=AStringThatIsTheLongAPIKeyFromSomeService
def load_env():
    _ = load_dotenv(find_dotenv())

class TerraformAnalysisResult(BaseModel):
    """Model representing the results of the Terraform analysis"""
    resources: List[str] = Field(default_factory=list, description="List of unique AWS resource types and custom modules found")
    error: Optional[str] = Field(default=None, description="Error message if analysis failed")

def get_terraform_files(directory_path: str) -> List[str]:
    """Find all Terraform files in the given directory and its subdirectories"""
    terraform_files = []

    # Look for .tf and .tf.json files
    for extension in ["*.tf", "*.tf.json"]:
        terraform_files.extend(
            glob.glob(os.path.join(directory_path, "**", extension), recursive=True)
        )

    return terraform_files

def read_file_contents(file_paths: List[str]) -> dict:
    """Read the contents of all files and return a dict mapping file paths to contents"""
    file_contents = {}

    for file_path in file_paths:
        try:
            with open(file_path, 'r') as file:
                file_contents[file_path] = file.read()
        except Exception as e:
            print(f"Error reading file {file_path}: {str(e)}")

    return file_contents

def analyze_terraform_with_openai(file_contents: dict, api_key: str) -> TerraformAnalysisResult:
    """Use OpenAI to analyze Terraform files and extract unique AWS resource types and custom modules"""

    # Create the prompt for OpenAI
    prompt = """
    Analyze the following Terraform code and extract:
    1. All AWS resource types used (e.g., aws_s3_bucket, aws_ec2_instance)
    2. All custom modules used
    
    For custom modules, extract the module name from the source attribute. For example:
    - If you see `source = "tfe.mycompany.com/MODULE-REGISTRY/rds-aurora-postgres/aws"`, extract "rds-aurora-postgres"
    - If you see `source = "./modules/vpc"`, extract "vpc"
    - If you see `source = "terraform-aws-modules/security-group/aws"`, extract "security-group"
    
    Extract the last meaningful component from the path, ignoring registry paths and provider names.
    
    Return ONLY a JSON object with a single array called "resources" containing both AWS resource types and module names, with no duplicates.
    The response should look like this:
    {
        "resources": ["aws_s3_bucket", "aws_ec2_instance", "rds-aurora-postgres", "vpc"]
    }
    
    Include both AWS resources (those starting with 'aws_') and the extracted module names.
    Ensure each item appears exactly once in the list (no duplicates).
    Do not include any other information - just the resource types and module names.
    
    Here are the Terraform files to analyze:
    
    """

    # Add file contents to the prompt
    for file_path, content in file_contents.items():
        prompt += f"\n--- File: {file_path} ---\n{content}\n"

    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=api_key)

        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",  # Use an appropriate model
            messages=[
                {"role": "system", "content": "You are a Terraform expert that analyzes infrastructure code and extracts unique AWS resource types and custom modules in a structured format."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )

        # Parse the response
        result_json = response.choices[0].message.content

        # Parse the result into our Pydantic model
        result = TerraformAnalysisResult.model_validate_json(result_json)
        return result

    except Exception as e:
        return TerraformAnalysisResult(
            resources=[],
            error=f"Error analyzing Terraform code: {str(e)}"
        )

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Analyze Terraform code to extract unique AWS resource types and custom modules using OpenAI')
    parser.add_argument('--directory', help='Directory containing Terraform code')
    # parser.add_argument('--api-key', help='OpenAI API key', default=os.environ.get('OPENAI_API_KEY'))
    args = parser.parse_args()

    # Validate inputs
    if not os.path.isdir(args.directory):
        print(f"Error: {args.directory} is not a valid directory")
        return

    # if not args.api_key:
    #     print("Error: OpenAI API key is required. Provide it via --api-key or set OPENAI_API_KEY environment variable.")
    #     return

    # Get all Terraform files
    terraform_files = get_terraform_files(args.directory)
    if not terraform_files:
        print(f"No Terraform files found in {args.directory}")
        return

    print(f"Found {len(terraform_files)} Terraform files")

    # Read file contents
    file_contents = read_file_contents(terraform_files)

    load_env()
    openai_api_key = os.getenv("OPENAI_API_KEY")

    # Analyze with OpenAI
    print("Analyzing Terraform code with OpenAI...")
    result = analyze_terraform_with_openai(file_contents, openai_api_key)

    # Check for errors
    if result.error:
        print(f"Analysis failed: {result.error}")
        return

    # Print results
    print(f"Found {len(result.resources)} unique AWS resources and custom modules:")
    print(result.resources)

if __name__ == "__main__":
    main()