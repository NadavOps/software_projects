import json
import hcl2
import boto3
import sys
import argparse
import pprint
import subprocess
import os

def argument_parsing():
    parser = argparse.ArgumentParser(description='Generate and run Terraform/Terragrunt import commands for AWS IAM resources.')
    parser.add_argument('-t', '--terraform_dir', type=str, help='Path to the Terraform directory containing the configuration files')
    parser.add_argument('-g', '--terragrunt_dir', type=str, default=None, help='Path to the Terragrunt directory containing the configuration files (optional)')
    parser.add_argument('-d', '--dry_run', action='store_true', help='Perform a dry run (only print commands, do not execute)')
    arguments = parser.parse_args()
    if not arguments.terraform_dir:
        parser.print_help()
        print(f'\nERROR: the flag \"--terraform_dir\" or \"-t\" is required')
        sys.exit(1)

    return arguments

class TFResourceFinder:
    def __init__(self, terraform_dir, terragrunt_dir=None, dry_run=False):
        self.terraform_dir = terraform_dir
        self.terragrunt_dir = terragrunt_dir
        self.dry_run = dry_run
        if self.terragrunt_dir:
            self.binary = "terragrunt"
            self.working_dir_flag = "--terragrunt-working-dir"
        else:
            self.binary = "terraform"
            self.working_dir_flag = "-chdir"
        self.account_id = self.__get_aws_account_id()
        self.new_declared_resources = self.__find_new_declared_resources()

    def __get_aws_account_id(self):
        sts_client = boto3.client('sts')
        response = sts_client.get_caller_identity()
        return response['Account']

    def __set_import_parameters(self, directory):
        self.import_directory_location = directory
        relative_path = os.path.relpath(directory, self.terraform_dir)

        if self.terragrunt_dir:
            self.import_directory_location = f"{self.terragrunt_dir}/{relative_path}"

        self.binary_working_dir = f'{self.working_dir_flag}={self.import_directory_location}'

    def __get_state_output(self, directory):
        self.__set_import_parameters(directory)
        print(f"getting state in {self.import_directory_location}")
        result = subprocess.run([self.binary, self.binary_working_dir, 'state', 'pull'], check=True, stdout=subprocess.PIPE, text=True)
        state_output = json.loads(result.stdout)
        return state_output
    
    def __get_state_resources(self, state_output):
        output_resources = {}

        for resource in state_output['resources']:
            tf_resource_type = resource['type']
            tf_resource_name = resource['name']
            if tf_resource_type not in output_resources:
                output_resources[tf_resource_type] = []
            
            output_resources[tf_resource_type].append(tf_resource_name)

        return output_resources
    
    def __is_resource_already_in_state(self, state_resources, tf_resource_type, tf_resource_name):
        if tf_resource_name in state_resources[tf_resource_type]:
            return True
        return False

    def __find_new_declared_resources(self):
        new_formed_resources = {}

        for root, dirs, files in os.walk(self.terraform_dir):
            print(f"Looking in {root}")

            for file in files:
                if file.endswith(".tf"):
                    state_output = self.__get_state_output(root)
                    state_resources = self.__get_state_resources(state_output)
                    break

            for file in files:
                if file.endswith(".tf"):
                    file_path = os.path.join(root, file)
                    with open(file_path, 'r') as tf_file:
                        content = hcl2.load(tf_file)

                    for resource_item in content.get('resource', []):
                        # resource_item is a dictionary with a single key (resource type)
                        for resource_type, resources in resource_item.items():
                            for resource_name, resource_fields in resources.items():

                                if self.__is_resource_already_in_state(state_resources, resource_type, resource_name):
                                    # print(f"skipping {resource_type}.{resource_name}")
                                    continue

                                if resource_type not in new_formed_resources:
                                    new_formed_resources[resource_type] = {}
                            
                                for field, value in resource_fields.items():
                                    if resource_name not in new_formed_resources[resource_type]:
                                        new_formed_resources[resource_type][resource_name] = {}

                                    new_formed_resources[resource_type][resource_name][field] = value

                                new_formed_resources[resource_type][resource_name]['custom_field_dir_location'] = root

        return new_formed_resources
    
    def __form_string_for_import_resource_command(self, resource_type, resource_name, fields):
        if fields['name']:
            name_value = fields['name']
            if str(name_value).startswith("${") and str(name_value).endswith("}"):
                variable_reference = str(name_value).strip("${}").split('.')
                name_value = self.new_declared_resources[variable_reference[0]][variable_reference[1]][variable_reference[2]]
        
        if resource_type == "aws_iam_role":
            return name_value
        
        if resource_type == "aws_iam_instance_profile":
            return name_value
            
        if resource_type == "aws_iam_policy":
            path_value = "/"
            if fields['path']:
                path_value = fields['path']
            return f'arn:aws:iam::{self.account_id}:policy{path_value}{name_value}'

        if resource_type == "aws_ecr_repository":
            return name_value
        
        user_input = input(f"Resource type \"{resource_type}\" is not supported. press yes to continue anyway")
        if user_input != 'yes':
            print("Exiting.")
            sys.exit(0)
        
    
    def show_current_resources(self):
        pprint.pprint(self.new_declared_resources)

    def import_resources(self):
        for resource_type, resources in self.new_declared_resources.items():
            for resource_name, fields in resources.items():
                self.__set_import_parameters(self.new_declared_resources[resource_type][resource_name]['custom_field_dir_location'])
                resource_import_string_suffix = self.__form_string_for_import_resource_command(resource_type, resource_name, fields)
                import_compant=f"{self.binary} {self.binary_working_dir} import {resource_type}.{resource_name} {resource_import_string_suffix}"
                print(import_compant)
                if not self.dry_run:
                    subprocess.run(import_compant, shell=True, executable='/bin/bash')

def main():
    args = argument_parsing()
    tf_resource_finder = TFResourceFinder(args.terraform_dir, args.terragrunt_dir, args.dry_run)
    tf_resource_finder.import_resources()

if __name__ == "__main__":
    main()
