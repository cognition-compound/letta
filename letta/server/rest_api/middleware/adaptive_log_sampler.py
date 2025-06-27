"""Adaptive log sampling utility for intelligent log volume reduction."""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Union
import threading


class SamplingStrategy(Enum):
    """Different sampling strategies available."""
    ALWAYS = "always"  # Log everything (no sampling)
    NEVER = "never"    # Log nothing
    RATE_BASED = "rate_based"  # Sample based on fixed rate
    ADAPTIVE = "adaptive"  # Adapt based on system load and error rates
    ERROR_BIASED = "error_biased"  # Always log errors, sample others


@dataclass
class SamplingConfig:
    """Configuration for adaptive log sampling."""
    strategy: SamplingStrategy = SamplingStrategy.ADAPTIVE
    base_sample_rate: float = 0.1  # Base sampling rate (10%)
    error_sample_rate: float = 1.0  # Always sample errors (100%)
    warning_sample_rate: float = 0.5  # Sample warnings at 50%
    debug_sample_rate: float = 0.01  # Sample debug messages at 1%
    
    # Adaptive parameters
    max_logs_per_second: int = 100  # Maximum logs per second before reducing sampling
    adaptive_window_seconds: int = 60  # Time window for calculating rates
    load_threshold: float = 0.8  # System load threshold to reduce sampling
    
    # Rate limits per log level
    max_debug_per_second: int = 10
    max_info_per_second: int = 50
    max_warning_per_second: int = 100
    # Errors are never rate limited


class AdaptiveLogSampler:
    """
    Intelligent log sampler that adapts based on system load and error rates.
    
    Features:
    - Always logs errors and critical messages
    - Reduces sampling rate during high load
    - Tracks log rates per level
    - Thread-safe for concurrent access
    """
    
    def __init__(self, config: Optional[SamplingConfig] = None):
        self.config = config or SamplingConfig()
        self._lock = threading.Lock()
        self._last_reset = time.time()
        
        # Counters for rate tracking
        self._log_counts: Dict[int, int] = {
            logging.DEBUG: 0,
            logging.INFO: 0,
            logging.WARNING: 0,
            logging.ERROR: 0,
            logging.CRITICAL: 0,
        }
        
        # Rate tracking for adaptive sampling
        self._recent_rates: Dict[int, float] = {
            logging.DEBUG: 0.0,
            logging.INFO: 0.0,
            logging.WARNING: 0.0,
            logging.ERROR: 0.0,
            logging.CRITICAL: 0.0,
        }
        
        # System load tracking (simplified)
        self._recent_log_rate = 0.0
        self._total_logs_in_window = 0
    
    def should_log(self, level: int, message: str = "") -> bool:
        """
        Determine if a log message should be logged based on sampling strategy.
        
        Args:
            level: Logging level (logging.DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: Optional message content for context-aware sampling
            
        Returns:
            bool: True if the message should be logged
        """
        with self._lock:
            # Update rates and reset counters if needed
            self._update_rates()
            
            # Always log errors and critical messages
            if level >= logging.ERROR:
                self._increment_counter(level)
                return True
            
            # Apply strategy-specific logic
            if self.config.strategy == SamplingStrategy.ALWAYS:
                self._increment_counter(level)
                return True
            elif self.config.strategy == SamplingStrategy.NEVER:
                return False
            elif self.config.strategy == SamplingStrategy.ERROR_BIASED:
                return self._should_log_error_biased(level)
            elif self.config.strategy == SamplingStrategy.RATE_BASED:
                return self._should_log_rate_based(level)
            elif self.config.strategy == SamplingStrategy.ADAPTIVE:
                return self._should_log_adaptive(level, message)
            
            # Default to rate-based if unknown strategy
            return self._should_log_rate_based(level)
    
    def _should_log_error_biased(self, level: int) -> bool:
        """Error-biased sampling: always log errors, sample others."""
        if level >= logging.ERROR:
            self._increment_counter(level)
            return True
        elif level == logging.WARNING:
            if self._should_sample(self.config.warning_sample_rate):
                self._increment_counter(level)
                return True
        elif level == logging.DEBUG:
            if self._should_sample(self.config.debug_sample_rate):
                self._increment_counter(level)
                return True
        else:  # INFO
            if self._should_sample(self.config.base_sample_rate):
                self._increment_counter(level)
                return True
        
        return False
    
    def _should_log_rate_based(self, level: int) -> bool:
        """Fixed rate-based sampling."""
        rate = self._get_sample_rate_for_level(level)
        if self._should_sample(rate):
            self._increment_counter(level)
            return True
        return False
    
    def _should_log_adaptive(self, level: int, message: str) -> bool:
        """Adaptive sampling based on current system load and log rates."""
        # Check rate limits first
        if not self._check_rate_limit(level):
            return False
        
        # Get base sample rate for this level
        base_rate = self._get_sample_rate_for_level(level)
        
        # Adjust rate based on current load
        adjusted_rate = self._adjust_rate_for_load(base_rate, level)
        
        # Apply context-aware adjustments
        adjusted_rate = self._adjust_rate_for_context(adjusted_rate, level, message)
        
        if self._should_sample(adjusted_rate):
            self._increment_counter(level)
            return True
        
        return False
    
    def _check_rate_limit(self, level: int) -> bool:
        """Check if we're within rate limits for this log level."""
        current_rate = self._recent_rates.get(level, 0.0)
        
        if level == logging.DEBUG and current_rate > self.config.max_debug_per_second:
            return False
        elif level == logging.INFO and current_rate > self.config.max_info_per_second:
            return False
        elif level == logging.WARNING and current_rate > self.config.max_warning_per_second:
            return False
        # Errors are never rate limited
        
        return True
    
    def _adjust_rate_for_load(self, base_rate: float, level: int) -> float:
        """Adjust sampling rate based on current system load."""
        if self._recent_log_rate > self.config.max_logs_per_second:
            # System is under high log load, reduce sampling
            load_factor = min(self.config.max_logs_per_second / self._recent_log_rate, 1.0)
            
            # Reduce more aggressively for debug/info, less for warnings
            if level == logging.DEBUG:
                return base_rate * load_factor * 0.5  # More aggressive reduction
            elif level == logging.INFO:
                return base_rate * load_factor * 0.7
            elif level == logging.WARNING:
                return base_rate * load_factor * 0.9  # Less aggressive reduction
        
        return base_rate
    
    def _adjust_rate_for_context(self, rate: float, level: int, message: str) -> float:
        """Adjust sampling rate based on message content."""
        # Increase sampling for potentially important messages
        important_keywords = ["error", "fail", "exception", "timeout", "unauthorized", "forbidden"]
        
        if any(keyword in message.lower() for keyword in important_keywords):
            return min(rate * 2.0, 1.0)  # Double the rate but cap at 100%
        
        return rate
    
    def _get_sample_rate_for_level(self, level: int) -> float:
        """Get the configured sample rate for a log level."""
        if level >= logging.ERROR:
            return self.config.error_sample_rate
        elif level == logging.WARNING:
            return self.config.warning_sample_rate  
        elif level == logging.DEBUG:
            return self.config.debug_sample_rate
        else:  # INFO
            return self.config.base_sample_rate
    
    def _should_sample(self, rate: float) -> bool:
        """Determine if we should sample based on the given rate."""
        import random
        return random.random() < rate
    
    def _increment_counter(self, level: int) -> None:
        """Increment the counter for a log level."""
        self._log_counts[level] = self._log_counts.get(level, 0) + 1
        self._total_logs_in_window += 1
    
    def _update_rates(self) -> None:
        """Update recent log rates and reset counters if needed."""
        now = time.time()
        elapsed = now - self._last_reset
        
        if elapsed >= self.config.adaptive_window_seconds:
            # Calculate rates
            for level in self._log_counts:
                self._recent_rates[level] = self._log_counts[level] / elapsed
            
            # Calculate total rate
            self._recent_log_rate = self._total_logs_in_window / elapsed
            
            # Reset counters
            self._log_counts = {level: 0 for level in self._log_counts}
            self._total_logs_in_window = 0
            self._last_reset = now
    
    def get_stats(self) -> Dict[str, Union[float, int]]:
        """Get current sampling statistics."""
        with self._lock:
            self._update_rates()
            return {
                "strategy": self.config.strategy.value,
                "total_log_rate": self._recent_log_rate,
                "debug_rate": self._recent_rates[logging.DEBUG],
                "info_rate": self._recent_rates[logging.INFO],
                "warning_rate": self._recent_rates[logging.WARNING], 
                "error_rate": self._recent_rates[logging.ERROR],
                "critical_rate": self._recent_rates[logging.CRITICAL],
                "window_seconds": self.config.adaptive_window_seconds,
            }
    
    def reset_stats(self) -> None:
        """Reset all statistics and counters."""
        with self._lock:
            self._log_counts = {level: 0 for level in self._log_counts}
            self._recent_rates = {level: 0.0 for level in self._recent_rates}
            self._total_logs_in_window = 0
            self._recent_log_rate = 0.0
            self._last_reset = time.time()


# Global singleton instance for easy access
_global_sampler: Optional[AdaptiveLogSampler] = None


def get_global_sampler() -> AdaptiveLogSampler:
    """Get the global log sampler instance."""
    global _global_sampler
    if _global_sampler is None:
        _global_sampler = AdaptiveLogSampler()
    return _global_sampler


def set_global_sampler(sampler: AdaptiveLogSampler) -> None:
    """Set the global log sampler instance."""
    global _global_sampler
    _global_sampler = sampler


def should_log_message(level: int, message: str = "") -> bool:
    """Convenience function to check if a message should be logged."""
    return get_global_sampler().should_log(level, message)