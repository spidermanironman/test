import sys

def validate_input(user_input):
    if not user_input:
        return False, "Input cannot be empty."
    
    if not user_input.isdigit():
        return False, "Input must be a positive integer."
        
    return True, "Input is valid."

def main():
    if len(sys.argv) > 1:
        user_input = sys.argv[1]
    else:
        print("Please provide input as an argument.")
        sys.exit(1)

    is_valid, message = validate_input(user_input)
    print(f"Input: '{user_input}'")
    print(f"Result: {message}")
    
    if not is_valid:
        sys.exit(1)

if __name__ == "__main__":
    main()
