import subprocess

def set_cpu_governor(number):
    """
    This function sets the CPU governor based on the input number. 
    The function takes an integer input and adjusts the CPU frequency governor
    for all cores accordingly:

    - If the input number is between 1 and 3 (inclusive), it sets the governor to 'performance'.
    - If the input number is between 4 and 7 (inclusive), it sets the governor to 'ondemand'.
    - If the input number is between 8 and 10 (inclusive), it sets the governor to 'powersave'.

    The function handles any potential errors using try-except blocks and 
    prints the corresponding command to the console without executing it.
    """

    try:
        # Check the range of the input number and set the appropriate governor
        if 1 <= number <= 3:
            governor = 'performance'
        elif 4 <= number <= 7:
            governor = 'ondemand'
        elif 8 <= number <= 10:
            governor = 'powersave'
        else:
            raise ValueError("Number must be between 1 and 10.")

        # Create the cpufreq-set command for all CPU cores
        command = f"cpufreq-set -g {governor}"
        print(f"Command to be executed: {command}")

    except ValueError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
