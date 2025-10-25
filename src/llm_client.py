"""
Ollama LLM client for AI-powered paper filtering.

This module provides a client for interacting with local Ollama models
to classify papers using LLM-based analysis.
"""

import logging
import json
import time
import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import hashlib
import requests

from .models import Paper


logger = logging.getLogger(__name__)


class OllamaClient:
    """
    Client for Ollama API for local LLM inference.
    
    Features:
    - Multi-filter analysis in single API call
    - Response caching to avoid redundant calls
    - Retry logic with exponential backoff
    - Usage tracking
    - No rate limits - runs locally on HPC
    """
    
    def __init__(
        self, 
        model: str = "llama3.1",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.0,
        cache_dir: Optional[Path] = None,
        retry_attempts: int = 3
    ):
        """
        Initialize Ollama client.
        
        Args:
            model: Model to use (must be available in Ollama)
            base_url: Ollama server URL (default: localhost)
            temperature: Sampling temperature (0.0 for deterministic)
            cache_dir: Directory to cache responses (None = no caching)
            retry_attempts: Number of retry attempts on failure
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.temperature = temperature
        self.retry_attempts = retry_attempts
        
        # Setup caching
        self.cache_enabled = cache_dir is not None
        self.cache_dir = cache_dir
        if self.cache_enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Response caching enabled: {self.cache_dir}")
        
        # Usage tracking
        self.api_calls = 0
        self.cache_hits = 0
        self.failed_calls = 0
        
        # System prompt for paper filtering
        self.system_prompt = """You are a research assistant helping to filter academic papers for a systematic literature review. 
Analyze the paper's title and abstract carefully and answer YES or NO for each filter question.
Be conservative - only answer YES if you are confident based on the text provided.

CRITICAL: You MUST respond with ONLY valid JSON. Do not include any text, explanation, or tokens before or after the JSON object.

Required JSON format:
{
    "filter_name_1": {"answer": "YES", "confidence": 0.95, "reason": "brief explanation"},
    "filter_name_2": {"answer": "NO", "confidence": 0.8, "reason": "brief explanation"}
}

Rules:
- answer: must be exactly "YES" or "NO" (uppercase)
- confidence: must be a number between 0.0 and 1.0
- reason: brief text explanation (max 15 words)
- Include ALL filters mentioned in the user prompt
- Output ONLY the JSON object - no preamble, no commentary, no extra tokens"""
    
    def _get_cache_key(self, paper: Paper, filters: Dict[str, str]) -> str:
        """Generate cache key for a paper and filter set."""
        content = f"{paper.title}|{paper.abstract}|{json.dumps(filters, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _load_from_cache(self, cache_key: str) -> Optional[Dict]:
        """Load response from cache if available."""
        if not self.cache_enabled:
            return None
        
        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    self.cache_hits += 1
                    logger.debug(f"Cache hit for key {cache_key[:8]}...")
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache file {cache_file}: {e}")
        
        return None
    
    def _save_to_cache(self, cache_key: str, response: Dict):
        """Save response to cache."""
        if not self.cache_enabled:
            return
        
        cache_file = self.cache_dir / f"{cache_key}.json"
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(response, f, indent=2)
            logger.debug(f"Cached response for key {cache_key[:8]}...")
        except Exception as e:
            logger.warning(f"Failed to save cache file {cache_file}: {e}")
    
    def _create_user_prompt(self, paper: Paper, filters: Dict[str, str]) -> str:
        """
        Create user prompt for multi-filter analysis.
        
        Args:
            paper: Paper to analyze
            filters: Dict mapping filter names to questions
        
        Returns:
            Formatted prompt string
        """
        # Format filter questions
        filter_questions = "\n".join([
            f"- {name}: {question}" 
            for name, question in filters.items()
        ])
        
        prompt = f"""Title: {paper.title}

Abstract: {paper.abstract or "[No abstract available]"}

Please answer YES or NO for each of the following filter questions:

{filter_questions}

Remember to respond with valid JSON only."""
        
        return prompt
    
    def _parse_response(self, response_text: str) -> Dict:
        """
        Parse LLM response into structured format.
        
        Args:
            response_text: Raw response from LLM
        
        Returns:
            Parsed response dict
        
        Raises:
            ValueError: If response cannot be parsed
        """
        # Log the raw response for debugging
        logger.debug(f"Raw LLM response: {response_text[:500]}")
        
        # Try to extract JSON from response
        try:
            # First try direct parsing
            result = json.loads(response_text.strip())
            return result
        except json.JSONDecodeError:
            # Try to find JSON in the text (look for outermost braces)
            # Search for the last complete JSON object since model may generate garbage before/after
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            
            if start != -1 and end > start:
                json_str = response_text[start:end]
                
                # Clean up common garbage patterns that break JSON
                # Remove tokens like [the) [0 that appear in the middle
                import re
                # Strategy: Find the largest valid JSON substring by removing corrupted parts
                
                # Try multiple extraction strategies
                for attempt_json in [json_str, json_str.split('\n\n')[-1] if '\n\n' in json_str else json_str]:
                    # Clean obvious garbage tokens - expanded patterns
                    cleaned = re.sub(
                        r'\[the\)|\[d\)|\[S\)|\[1\)|\[0\)|\[C\)|\[F\)|\*\*\[?|<<[^\s]+|\[and/or|~<|\(the\)|\)the\)|##<',
                        '', 
                        attempt_json
                    )
                    # Remove excessive repetitions like ))))))))
                    cleaned = re.sub(r'(\)|\s)\1{5,}', '', cleaned)
                    
                    try:
                        result = json.loads(cleaned)
                        logger.debug("Successfully parsed after cleaning")
                        return result
                    except json.JSONDecodeError:
                        pass
                
                # Try finding nested JSON if cleaning didn't work
                # Look for pattern: "filter_name": {...} to reconstruct
                try:
                    # Extract all complete filter entries
                    filter_pattern = r'"(\w+)":\s*\{[^}]*"answer":\s*"(YES|NO)"[^}]*"confidence":\s*([\d.]+)[^}]*"reason":\s*"([^"]+)"[^}]*\}'
                    matches = re.findall(filter_pattern, json_str, re.DOTALL)
                    
                    if matches:
                        reconstructed = {}
                        for filter_name, answer, confidence, reason in matches:
                            reconstructed[filter_name] = {
                                "answer": answer,
                                "confidence": float(confidence),
                                "reason": reason
                            }
                        if reconstructed:
                            logger.debug(f"Reconstructed JSON from {len(matches)} filter matches")
                            return reconstructed
                except Exception as e:
                    logger.debug(f"Reconstruction attempt failed: {e}")
                
                # Last attempt: manual parse the original
                try:
                    result = json.loads(json_str)
                    return result
                except json.JSONDecodeError as e:
                    logger.debug(f"JSON parse error: {e}")
                    logger.debug(f"Attempted to parse: {json_str[:200]}")
            
            # If all parsing fails, show what we got
            logger.error(f"Full response text: {response_text}")
            raise ValueError(f"Could not parse JSON from response. First 500 chars: {response_text[:500]}")
    
    def check_paper(
        self, 
        paper: Paper, 
        filters: Dict[str, str]
    ) -> Dict:
        """
        Check a paper against multiple filters in one API call.
        
        Args:
            paper: Paper to analyze
            filters: Dict mapping filter names to filter questions
        
        Returns:
            Dict with structure:
            {
                'success': bool,
                'filters': {
                    'filter_name': {
                        'should_filter': bool,
                        'confidence': float,
                        'reason': str
                    },
                    ...
                },
                'error': Optional[str],
                'manual_review': bool
            }
        """
        # Check cache first
        cache_key = self._get_cache_key(paper, filters)
        cached = self._load_from_cache(cache_key)
        if cached is not None:
            return cached
        
        # Prepare prompt
        user_prompt = self._create_user_prompt(paper, filters)
        
        # Try API call with retries
        for attempt in range(self.retry_attempts):
            try:
                # Call Ollama API using /api/generate (more compatible than /api/chat)
                # Combine system and user prompts since /api/generate doesn't use messages
                combined_prompt = f"{self.system_prompt}\n\n{user_prompt}"
                
                response = requests.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": combined_prompt,
                        "stream": False,
                        "options": {
                            "temperature": self.temperature,
                        }
                    },
                    timeout=120  # 2 minutes timeout for HPC
                )
                
                response.raise_for_status()
                self.api_calls += 1
                
                # Parse response
                response_data = response.json()
                response_text = response_data['response']  # /api/generate uses 'response' not 'message'
                parsed = self._parse_response(response_text)
                
                # Convert to our format
                result = {
                    'success': True,
                    'filters': {},
                    'error': None,
                    'manual_review': False
                }
                
                for filter_name in filters.keys():
                    if filter_name in parsed:
                        filter_result = parsed[filter_name]
                        should_filter = filter_result.get('answer', 'NO').upper() == 'YES'
                        confidence = float(filter_result.get('confidence', 0.5))
                        reason = filter_result.get('reason', 'No reason provided')
                        
                        result['filters'][filter_name] = {
                            'should_filter': should_filter,
                            'confidence': confidence,
                            'reason': reason
                        }
                    else:
                        # Missing filter in response - use conservative default (keep paper)
                        logger.warning(f"Filter '{filter_name}' not in response for paper: {paper.title[:50]}")
                        result['filters'][filter_name] = {
                            'should_filter': False,  # Conservative: don't filter if unsure
                            'confidence': 0.0,
                            'reason': 'Missing from LLM response - keeping paper'
                        }
                        # Only flag for manual review if MULTIPLE filters are missing
                        missing_count = sum(1 for fname in filters.keys() if fname not in parsed)
                        if missing_count >= 2:  # 2 or more filters missing = needs review
                            result['manual_review'] = True
                
                # Cache successful response
                self._save_to_cache(cache_key, result)
                
                return result
                
            except Exception as e:
                logger.warning(f"API call attempt {attempt + 1}/{self.retry_attempts} failed: {e}")
                
                if attempt < self.retry_attempts - 1:
                    # Exponential backoff
                    wait_time = 2 ** attempt
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    # All attempts failed
                    self.failed_calls += 1
                    logger.error(f"All retry attempts failed for paper: {paper.title[:50]}")
                    
                    result = {
                        'success': False,
                        'filters': {},
                        'error': str(e),
                        'manual_review': True  # Flag for manual review
                    }
                    
                    # Create default "keep" responses for all filters
                    for filter_name in filters.keys():
                        result['filters'][filter_name] = {
                            'should_filter': False,
                            'confidence': 0.0,
                            'reason': f'API error: {str(e)[:50]}'
                        }
                    
                    return result
    
    def get_usage_stats(self) -> Dict:
        """
        Get usage statistics.
        
        Returns:
            Dict with API call counts and cache statistics
        """
        total_requests = self.api_calls + self.cache_hits
        cache_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'api_calls': self.api_calls,
            'cache_hits': self.cache_hits,
            'failed_calls': self.failed_calls,
            'total_requests': total_requests,
            'cache_hit_rate': f"{cache_rate:.1f}%",
            'model': self.model
        }
