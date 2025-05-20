import os
import glob
from pathlib import Path
from typing import List, Optional
import argparse
from pydantic import BaseModel, Field
from crewai import Agent, Task, Crew
from langchain_openai import ChatOpenAI

from dotenv import load_dotenv, find_dotenv

# these expect to find a .env file at the directory above the lesson.                                                                                                                     # the format for that file is (without the comment)                                                                                                                                       #API_KEYNAME=AStringThatIsTheLongAPIKeyFromSomeService
def load_env():
    _ = load_dotenv(find_dotenv())

class TerraformAnalysisResult(BaseModel):
    """Model representing the results of the Terraform analysis"""
    resources: List[str] = Field(default_factory=list, description="List of unique AWS resource types and custom modules found")

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

def analyze_terraform_with_crew(directory_path: str, api_key: str) -> List[str]:
    """
    Use crewAI to analyze Terraform files and extract AWS resources and custom modules
    """
    # Get all Terraform files
    terraform_files = get_terraform_files(directory_path)
    if not terraform_files:
        print(f"No Terraform files found in {directory_path}")
        return []

    # Read file contents
    file_contents = read_file_contents(terraform_files)

    # Prepare terraform code for analysis
    terraform_code = ""
    for file_path, content in file_contents.items():
        terraform_code += f"\n--- File: {file_path} ---\n{content}\n"

    # Create LLM
    llm = ChatOpenAI(
        api_key=api_key,
        model="gpt-4-turbo-preview",
        temperature=0
    )

    # Create Agent
    terraform_analyzer = Agent(
        role="Terraform Expert",
        goal="Extract AWS resources and custom modules from Terraform code",
        backstory="You are an expert in Terraform who can analyze infrastructure code and identify all AWS resources and custom modules used.",
        verbose=True,
        llm=llm
    )

    # Create Task
    analysis_task = Task(
        description=f"""
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
        {{
            "resources": ["aws_s3_bucket", "aws_ec2_instance", "rds-aurora-postgres", "vpc"]
        }}
        
        Include both AWS resources (those starting with 'aws_') and the extracted module names.
        Ensure each item appears exactly once in the list (no duplicates).
        Do not include any other information - just the resource types and module names.
        
        Here are the Terraform files to analyze:
        
        {terraform_code}
        """,
        agent=terraform_analyzer,
        expected_output="A JSON object with a 'resources' array containing unique AWS resource types and custom modules"
    )

    # Create Crew
    terraform_crew = Crew(
        agents=[terraform_analyzer],
        tasks=[analysis_task],
        verbose=1
    )

    # Execute the crew process and get the result
    result = terraform_crew.kickoff()

    # Parse the result to extract the list
    try:
        result_model = TerraformAnalysisResult.model_validate_json(result)
        return result_model.resources
    except Exception as e:
        # If direct JSON parsing fails, try to extract JSON from the text
        import re
        import json

        # Look for json pattern in the result
        json_pattern = r'\{[^{}]*\}'
        json_match = re.search(json_pattern, result)

        if json_match:
            try:
                json_dict = json.loads(json_match.group(0))
                if "resources" in json_dict:
                    return json_dict["resources"]
            except:
                pass

        # Last resort: look for array pattern in the result
        array_pattern = r'\[(.*?)\]'
        array_match = re.search(array_pattern, result)

        if array_match:
            try:
                # Extract the array contents and split by commas
                array_content = array_match.group(1)
                items = [item.strip(' "\'') for item in array_content.split(',')]
                return items
            except:
                pass

        print(f"Failed to parse result: {e}")
        print(f"Raw result: {result}")
        return []

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Analyze Terraform code to extract unique AWS resource types and custom modules using crewAI')
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

    load_env()
    openai_api_key = os.getenv("OPENAI_API_KEY")
    print(f"Analyzing Terraform code in {args.directory} with crewAI...")
    resources = analyze_terraform_with_crew(args.directory, openai_api_key)

    # Print results
    print(f"Found {len(resources)} unique AWS resources and custom modules:")
    print(resources)

if __name__ == "__main__":
    main()