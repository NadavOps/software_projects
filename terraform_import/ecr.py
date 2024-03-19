import re
import sys
import argparse
import subprocess
import os

def argument_parsing():
    parser = argparse.ArgumentParser(description='Generate and run Terraform/Terragrunt import commands for aws_ecr_repository resources.')
    parser.add_argument('-t', '--terraform_dir', type=str, help='Path to the Terraform directory containing the configuration files')
    parser.add_argument('-g', '--terragrunt_dir', type=str, help='Path to the Terragrunt directory containing the configuration files (optional)')
    parser.add_argument('-d', '--dry_run', action='store_true', help='Perform a dry run (only print commands, do not execute)')
    arguments = parser.parse_args()
    if not arguments.terraform_dir:
        parser.print_help()
        print(f'\nERROR: the flag \"--terraform_dir\" or \"-t\" is required')
        sys.exit(1)

    return arguments

def extract_ecr_repository_info(dir_path):
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            if file.endswith(".tf"):
                file_path = os.path.join(root, file)
                with open(file_path, 'r') as tf_file:
                    content = tf_file.read()

                # Use regular expression to find resource names with aws_ecr_repository type
                pattern = r'resource\s+"aws_ecr_repository"\s+"([^"]+)"\s+{[^}]+name\s+=\s+"([^"]+)"'
                matches = re.findall(pattern, content, re.DOTALL)

                for resource_name, repo_name in matches:
                    yield resource_name, repo_name, file

def generate_import_commands(repository_info, terragrunt_dir):
    import_commands = []
    for resource_name, repo_name, file_name in repository_info:
        cmd_prefix = 'terragrunt' if terragrunt_dir else 'terraform'
        cmd_prefix = f"cd {terragrunt_dir} && {cmd_prefix}" if terragrunt_dir else cmd_prefix
        import_commands.append(f"{cmd_prefix} import aws_ecr_repository.{resource_name} {repo_name}")

    return import_commands

def run_import_commands(import_commands, dry_run=False, dir_path=None):
    print(f"\nCurrent Directory: {dir_path}")
    for command in import_commands:
        print(f"\nCommand: {command}")
        if not dry_run:
            subprocess.run(command, shell=True, cwd=dir_path, executable='/bin/bash')

def main():
    args = argument_parsing()
    repository_info = extract_ecr_repository_info(args.terraform_dir)
    import_commands = generate_import_commands(repository_info, args.terragrunt_dir)

    run_import_commands(import_commands, dry_run=args.dry_run, dir_path=args.terraform_dir)

if __name__ == "__main__":
    main()
