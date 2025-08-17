import argparse
import time
import uuid
from enum import Enum
from typing import List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from openai.types.chat import ChatCompletion
from pydantic import BaseModel, Field
import uvicorn


class Role(str, Enum):
    """Role enumeration for chat messages."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    """Chat message model."""
    role: Role
    content: str


class ChatCompletionRequest(BaseModel):
    """Chat completion request model."""
    messages: List[Message] = Field(
        ..., 
        min_length=1, 
        description="The conversation messages history, in chronological order."
    )
    model: str = Field(..., description="The name of the model to use.")
    max_tokens: Optional[int] = Field(
        default=256,
        description="Maximum number of tokens to generate in the response."
    )
    temperature: Optional[float] = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature to use. Higher values make output more random."
    )
    user: Optional[str] = Field(
        default=None,
        description="Unique identifier for the end-user to help with monitoring or abuse detection."
    )
    stream: Optional[bool] = Field(
        default=False,
        description="If true, return streamed responses as data-only server-sent events."
    )

    model_config = {
        "extra": "ignore",
        "json_schema_extra": {
            "examples": [
                {
                    "model": "fake_model_name",
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": "Hello, I'm Ifta"},
                        {
                            "role": "user",
                            "content": "What is my name? What is the capital of Bangladesh?",
                        },
                    ],
                    "temperature": 0.7,
                    "max_tokens": 128,
                    "n": 1,
                    "user": "user-123",
                }
            ]
        },
    }


class ChatCompletionResponse(ChatCompletion):
    """Chat completion response model."""
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "8aerio29048q4924ag32352r4",
                    "created": 1710000000,
                    "model": "fake_model_name",
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": (
                                    "Hello Ifta. It's nice to meet you.\n\n"
                                    "Your name is Ifta.\n\n"
                                    "The capital of Bangladesh is Dhaka."
                                ),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 25, "completion_tokens": 35, "total_tokens": 60},
                }
            ]
        }
    }


class FakeOpenAIServer:
    """Fake OpenAI server implementation."""
    
    def __init__(self, model_name: str = "fake_model_name", max_tokens: int = 100):
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.num_running_requests = 0
        self.app = FastAPI()
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup FastAPI routes."""
        self.app.post("/v1/chat/completions")(self.chat_completions)
        self.app.get("/v1/models")(self.models)
        self.app.get("/is_sleeping")(self.is_sleeping)
        self.app.get("/metrics")(self.metrics)
    
    def _generate_fake_content(self, messages: List[Message]) -> str:
        """Generate fake content based on the input messages."""
        user_messages = [msg for msg in messages if msg.role == Role.USER]
        if not user_messages:
            return "Hello! I'm a helpful assistant."
        
        last_user_message = user_messages[-1].content.lower()
        
        if "name" in last_user_message and "bangladesh" in last_user_message:
            return "Nice to meet you, Ifta. Your name is Ifta. The capital of Bangladesh is Dhaka."
        elif "name" in last_user_message:
            return "Nice to meet you, Ifta. Your name is Ifta."
        elif "bangladesh" in last_user_message:
            return "As for the capital of Bangladesh, it's Dhaka."
        elif "hello" in last_user_message:
            return "Hello! How can I help you today?"
        else:
            return "I understand your question. Let me provide a helpful response."
    
    def _generate_response_data(
        self, 
        request_id: str, 
        model_name: str, 
        messages: List[Message], 
        max_tokens: int
    ) -> dict:
        """Generate response data structure."""
        start_time = time.time()
        self.num_running_requests += 1
        
        try:
            content = self._generate_fake_content(messages)
            
            # Estimate token counts
            prompt_tokens = 64
            completion_tokens = min(30, max_tokens)
            total_tokens = prompt_tokens + completion_tokens
            
            response_data = {
                "id": request_id,
                "choices": [
                    {
                        "finish_reason": "stop",
                        "index": 0,
                        "logprobs": None,
                        "message": {
                            "content": content,
                            "refusal": None,
                            "role": "assistant",
                            "annotations": None,
                            "audio": None,
                            "function_call": None,
                            "tool_calls": [],
                            "reasoning_content": None
                        },
                        "stop_reason": None
                    }
                ],
                "created": int(time.time()),
                "model": model_name,
                "object": "chat.completion",
                "service_tier": None,
                "system_fingerprint": None,
                "usage": {
                    "completion_tokens": completion_tokens,
                    "prompt_tokens": prompt_tokens,
                    "total_tokens": total_tokens,
                    "completion_tokens_details": None,
                    "prompt_tokens_details": None
                },
                "prompt_logprobs": None,
                "kv_transfer_params": None
            }
            
            return response_data
            
        finally:
            self.num_running_requests -= 1
            elapsed = time.time() - start_time
            print(f"Finished request with id: {request_id}, elapsed time: {elapsed:.3f}s")
    
    async def chat_completions(self, request: ChatCompletionRequest, raw_request: Request) -> JSONResponse:
        """Handle chat completion requests."""
        request_id = f"chatcmpl-{uuid.uuid4()}"
        print(f"Received request with id: {request_id} at {time.time()}")
        
        model_name = request.model or self.model_name
        num_tokens = request.max_tokens or self.max_tokens
        
        response_data = self._generate_response_data(
            request_id, model_name, request.messages, num_tokens
        )
        return JSONResponse(content=response_data)
    
    async def models(self) -> JSONResponse:
        """Return available models endpoint."""
        models_data = {
            "object": "list",
            "data": [
                {
                    "id": self.model_name,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "vllm",
                    "root": None,
                    "parent": None
                }
            ]
        }
        return JSONResponse(content=models_data)
    
    async def is_sleeping(self) -> JSONResponse:
        """Return sleeping status endpoint."""
        return JSONResponse(content={"is_sleeping": False})
    
    async def metrics(self) -> Response:
        """Return metrics endpoint."""
        content = f"""# HELP vllm:num_requests_running Number of requests currently running on GPU.
                # TYPE vllm:num_requests_running gauge
                vllm:num_requests_running{{model_name="{self.model_name}"}} {self.num_running_requests}
                # HELP vllm:num_requests_swapped Number of requests swapped to CPU.
                # TYPE vllm:num_requests_swapped gauge
                vllm:num_requests_swapped{{model_name="{self.model_name}"}} 0.0
                # HELP vllm:num_requests_waiting Number of requests waiting to be processed.
                # TYPE vllm:num_requests_waiting gauge
                vllm:num_requests_waiting{{model_name="{self.model_name}"}} 0.0"""

        return Response(content=content, media_type="text/plain")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Fake OpenAI server for testing")
    parser.add_argument("--port", type=int, default=9000, help="Port to run the server on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind the server to")
    parser.add_argument("--max-tokens", type=int, default=100, help="Maximum tokens to generate")
    parser.add_argument("--speed", type=int, default=100, help="Number of tokens per second per request")
    parser.add_argument("--model-name", type=str, default="fake_model_name", help="Model name to use for the server")
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    server = FakeOpenAIServer(
        model_name=args.model_name,
        max_tokens=args.max_tokens
    )
    # You can access args.speed in your endpoints if needed
    uvicorn.run(
        server.app,
        host=args.host,
        port=args.port
    )


if __name__ == "__main__":
    main()