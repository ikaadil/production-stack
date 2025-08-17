#!/bin/bash

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <number of servers> <tokens/req/sec> [model1,model2,model3,...]"
    echo "Example: $0 4 500 llama-7b-chat,gpt-3.5-turbo,claude-3-haiku,mistral-7b"
    echo "If models not provided, will use fake_model_name for all servers"
    exit 1
fi

NUM_SERVERS="$1"
SPEED="$2"
MODELS_ARG="${3:-}"

# Default model names if not provided
DEFAULT_MODELS=("fake_model_name")

# Parse model names if provided
if [[ -n "$MODELS_ARG" ]]; then
    IFS=',' read -ra MODELS <<< "$MODELS_ARG"
else
    MODELS=("${DEFAULT_MODELS[@]}")
fi

for i in $(seq 1 "$NUM_SERVERS"); do
    # Use modulo to cycle through models if there are fewer models than servers
    MODEL_INDEX=$(( (i - 1) % ${#MODELS[@]} ))
    MODEL_NAME="${MODELS[$MODEL_INDEX]}"
    
    # Get the directory where this script is located
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    echo "Starting server $i on port 900$i with model: $MODEL_NAME"
    python3 "$SCRIPT_DIR/fake-openai-server.py" --port "900$i" --model-name "$MODEL_NAME" --speed "$SPEED" &
done

echo "Started $NUM_SERVERS servers"
