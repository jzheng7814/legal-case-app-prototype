"""
Tokenizer wrapper for consistent tokenization across all tools.
Supports different tokenizer backends (tiktoken, transformers, etc.).
"""

from typing import List, Tuple, Optional
import os


class TokenizerWrapper:
    """
    Wrapper for tokenization operations.
    Provides consistent interface regardless of underlying tokenizer.
    """
    
    def __init__(self, model_name: str = "gpt-4o"):
        """
        Initialize tokenizer for the specified model.
        
        Args:
            model_name: Name of the model to use for tokenization
                      Can be OpenAI model names (gpt-3.5-turbo, gpt-4, etc.)
                      or HuggingFace model names (Qwen/Qwen3-8B, meta-llama/Llama-2-7b-hf, etc.)
        """
        self.model_name = model_name
        self._tokenizer = None
        self._encoding = None
        self._backend = None
        
        # First, try HuggingFace transformers for models with '/' in name
        if '/' in model_name or model_name.startswith('Qwen'):
            try:
                from transformers import AutoTokenizer
                
                # Special handling for Qwen models
                if 'Qwen' in model_name:
                    # Qwen models require trust_remote_code=True
                    self._tokenizer = AutoTokenizer.from_pretrained(
                        model_name, 
                        trust_remote_code=True,  # Required for Qwen models
                        use_fast=True,  # Use fast tokenizer when available
                        padding_side='left',  # Qwen uses left padding
                        clean_up_tokenization_spaces=False  # Preserve spaces
                    )
                else:
                    self._tokenizer = AutoTokenizer.from_pretrained(
                        model_name, 
                        trust_remote_code=True,
                        use_fast=True
                    )
                
                self._backend = "transformers"
                # print(f"Loaded HuggingFace tokenizer for {model_name}")
                return
            except ImportError:
                pass
                # print("Warning: transformers not installed. Trying other backends.")
            except Exception as e:
                pass
                # print(f"Could not load HuggingFace tokenizer for {model_name}: {e}")
        
        # Try tiktoken for OpenAI models
        try:
            import tiktoken
            if model_name in ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4o"]:
                self._encoding = tiktoken.encoding_for_model(model_name)
            else:
                # Default to cl100k_base for unknown models
                self._encoding = tiktoken.get_encoding("cl100k_base")
            self._backend = "tiktoken"
            # print(f"Using tiktoken for {model_name}")
        except ImportError:
            pass
            # print("Warning: tiktoken not installed.")
        except Exception as e:
            pass
            # print(f"Could not initialize tiktoken: {e}")
        
        # Fall back to simple whitespace tokenization
        if self._backend is None:
            # print("Warning: Using simple whitespace tokenization as fallback.")
            self._backend = "simple"
    
    def encode(self, text: str) -> List[int]:
        """
        Encode text to token IDs.
        
        Args:
            text: Text to tokenize
            
        Returns:
            List of token IDs
        """
        if self._backend == "transformers" and self._tokenizer:
            # HuggingFace tokenizer
            encoded = self._tokenizer.encode(text, add_special_tokens=False)
            return encoded
        elif self._backend == "tiktoken" and self._encoding:
            return self._encoding.encode(text)
        else:
            # Simple whitespace tokenization (fallback)
            return list(range(len(text.split())))
    
    def decode(self, tokens: List[int]) -> str:
        """
        Decode token IDs back to text.
        
        Args:
            tokens: List of token IDs
            
        Returns:
            Decoded text
        """
        if self._backend == "transformers" and self._tokenizer:
            # HuggingFace tokenizer
            return self._tokenizer.decode(tokens, skip_special_tokens=True)
        elif self._backend == "tiktoken" and self._encoding:
            return self._encoding.decode(tokens)
        else:
            # Simple fallback - not accurate but prevents crashes
            return f"<{len(tokens)} tokens>"
    
    def count_tokens(self, text: str) -> int:
        """
        Count the number of tokens in text.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Number of tokens
        """
        return len(self.encode(text))
    
    def get_text_for_token_range(self, text: str, start_token: int, end_token: int) -> Tuple[str, int, int]:
        """
        Extract text corresponding to a token range.
        
        Args:
            text: Full text
            start_token: Starting token index (inclusive)
            end_token: Ending token index (exclusive)
            
        Returns:
            Tuple of (extracted_text, actual_start_token, actual_end_token)
        """
        if self._backend == "transformers" and self._tokenizer:
            # HuggingFace tokenizer
            tokens = self._tokenizer.encode(text, add_special_tokens=False)
            
            # Clamp to valid range
            start_token = max(0, min(start_token, len(tokens)))
            end_token = max(start_token, min(end_token, len(tokens)))
            
            # Get the text for this token range
            selected_tokens = tokens[start_token:end_token]
            extracted_text = self._tokenizer.decode(selected_tokens, skip_special_tokens=True)
            
            return extracted_text, start_token, end_token
        elif self._backend == "tiktoken" and self._encoding:
            tokens = self._encoding.encode(text)
            
            # Clamp to valid range
            start_token = max(0, min(start_token, len(tokens)))
            end_token = max(start_token, min(end_token, len(tokens)))
            
            # Get the text for this token range
            selected_tokens = tokens[start_token:end_token]
            extracted_text = self._encoding.decode(selected_tokens)
            
            return extracted_text, start_token, end_token
        else:
            # Simple fallback using character positions
            words = text.split()
            start_idx = max(0, min(start_token, len(words)))
            end_idx = max(start_idx, min(end_token, len(words)))
            extracted_text = " ".join(words[start_idx:end_idx])
            return extracted_text, start_idx, end_idx
