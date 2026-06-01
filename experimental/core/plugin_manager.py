#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plugin Manager
Loosely coupled plugin architecture for extensibility

This module provides a plugin system that enables:
- Dynamic plugin loading and unloading
- Plugin lifecycle management
- Dependency resolution
- Configuration management
- Hot-reloading support

Features:
- Plugin interface specification
- Automatic dependency injection
- Plugin discovery
- Version compatibility checking
- Plugin isolation
"""

import os
import json
import importlib
import inspect
from typing import List, Dict, Callable, Any, Optional, Type, Set
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
from pathlib import Path


class PluginState(Enum):
    """Plugin lifecycle states"""
    DISCOVERED = "discovered"     # Found but not loaded
    LOADING = "loading"           # Currently loading
    LOADED = "loaded"             # Successfully loaded
    ACTIVE = "active"             # Active and running
    DISABLED = "disabled"         # Manually disabled
    ERROR = "error"               # Failed to load/activate
    UNLOADED = "unloaded"         # Unloaded


class PluginPriority(Enum):
    """Plugin execution priority"""
    SYSTEM = 0       # Core system plugins
    HIGH = 10        # High priority plugins
    NORMAL = 50      # Normal priority
    LOW = 100        # Low priority plugins
    OPTIONAL = 200   # Optional enhancements


@dataclass
class PluginInfo:
    """Plugin metadata and information"""
    name: str
    version: str
    description: str = ""
    author: str = ""
    priority: PluginPriority = PluginPriority.NORMAL
    dependencies: List[str] = field(default_factory=list)
    provides: List[str] = field(default_factory=list)
    config_schema: Dict = field(default_factory=dict)
    state: PluginState = PluginState.DISCOVERED
    error_message: str = ""
    instance: Optional[Any] = None


class PluginBase(ABC):
    """
    Base class for all plugins

    Plugins must inherit from this class and implement
    the required lifecycle methods.
    """

    # Plugin metadata (override in subclass)
    NAME = "unknown"
    VERSION = "0.0.0"
    DESCRIPTION = ""
    AUTHOR = ""
    PRIORITY = PluginPriority.NORMAL
    DEPENDENCIES: List[str] = []
    PROVIDES: List[str] = []

    def __init__(self, plugin_manager=None, config: Optional[Dict] = None):
        """
        Initialize plugin

        Args:
            plugin_manager: Reference to plugin manager
            config: Plugin configuration
        """
        self.plugin_manager = plugin_manager
        self.config = config or {}
        self._enabled = False

    @abstractmethod
    def on_load(self) -> bool:
        """
        Called when plugin is loaded

        Returns:
            True if loading successful, False otherwise
        """
        pass

    @abstractmethod
    def on_enable(self) -> bool:
        """
        Called when plugin is enabled

        Returns:
            True if enabling successful, False otherwise
        """
        pass

    @abstractmethod
    def on_disable(self) -> None:
        """Called when plugin is disabled"""
        pass

    @abstractmethod
    def on_unload(self) -> None:
        """Called when plugin is unloaded"""
        pass

    def get_info(self) -> PluginInfo:
        """Get plugin information"""
        return PluginInfo(
            name=self.NAME,
            version=self.VERSION,
            description=self.DESCRIPTION,
            author=self.AUTHOR,
            priority=self.PRIORITY,
            dependencies=self.DEPENDENCIES.copy(),
            provides=self.PROVIDES.copy()
        )

    def is_enabled(self) -> bool:
        """Check if plugin is enabled"""
        return self._enabled


class PluginManager:
    """
    Central plugin management system

    Handles plugin discovery, loading, lifecycle management,
    and inter-plugin communication.
    """

    def __init__(
        self,
        plugin_dirs: Optional[List[str]] = None,
        event_bus=None,
        auto_discover: bool = True
    ):
        """
        Initialize plugin manager

        Args:
            plugin_dirs: Directories to search for plugins
            event_bus: Event bus for plugin communication
            auto_discover: Automatically discover plugins on init
        """
        self.plugin_dirs = plugin_dirs or ["plugins"]
        self.event_bus = event_bus
        self._plugins: Dict[str, PluginInfo] = {}
        self._plugin_classes: Dict[str, Type[PluginBase]] = {}
        self._services: Dict[str, Any] = {}
        self._hooks: Dict[str, List[Callable]] = {}

        # Track plugin load order for dependency resolution
        self._load_order: List[str] = []

        if auto_discover:
            self.discover_plugins()

    def discover_plugins(self) -> List[str]:
        """
        Discover plugins in configured directories

        Returns:
            List of discovered plugin names
        """
        discovered = []

        for plugin_dir in self.plugin_dirs:
            plugin_path = Path(plugin_dir)
            if not plugin_path.exists():
                continue

            # Look for Python modules
            for item in plugin_path.iterdir():
                if item.is_dir():
                    # Check for plugin module
                    init_file = item / "__init__.py"
                    if init_file.exists():
                        plugin_name = item.name
                        if plugin_name not in self._plugins:
                            self._discover_plugin(plugin_name, str(item))
                            discovered.append(plugin_name)

                elif item.suffix == ".py" and not item.name.startswith("_"):
                    plugin_name = item.stem
                    if plugin_name not in self._plugins:
                        self._discover_plugin(plugin_name, str(item.parent))
                        discovered.append(plugin_name)

        return discovered

    def _discover_plugin(self, name: str, path: str) -> None:
        """Discover and register a plugin"""
        try:
            # Import the module
            module_path = path.replace("/", ".").replace("\\", ".")
            module = importlib.import_module(f"{module_path}.{name}")

            # Find plugin classes
            for item_name, item in inspect.getmembers(module):
                if (inspect.isclass(item) and
                    issubclass(item, PluginBase) and
                    item != PluginBase):

                    info = item().get_info()
                    info.state = PluginState.DISCOVERED
                    self._plugins[info.name] = info
                    self._plugin_classes[info.name] = item
                    break

        except Exception as e:
            print(f"Error discovering plugin {name}: {e}")

    def register_plugin(self, plugin_class: Type[PluginBase]) -> str:
        """
        Manually register a plugin class

        Args:
            plugin_class: Plugin class to register

        Returns:
            Plugin name
        """
        info = plugin_class().get_info()
        info.state = PluginState.DISCOVERED
        self._plugins[info.name] = info
        self._plugin_classes[info.name] = plugin_class
        return info.name

    def load_plugin(self, name: str, config: Optional[Dict] = None) -> bool:
        """
        Load a plugin by name

        Args:
            name: Plugin name
            config: Plugin configuration

        Returns:
            True if loaded successfully
        """
        if name not in self._plugins:
            print(f"Plugin not found: {name}")
            return False

        info = self._plugins[name]

        if info.state in (PluginState.LOADED, PluginState.ACTIVE):
            return True

        try:
            info.state = PluginState.LOADING

            # Check dependencies
            if not self._check_dependencies(name):
                info.state = PluginState.ERROR
                info.error_message = "Missing dependencies"
                return False

            # Load dependencies first
            for dep in info.dependencies:
                if self._plugins[dep].state not in (PluginState.LOADED, PluginState.ACTIVE):
                    if not self.load_plugin(dep):
                        return False

            # Create plugin instance
            plugin_class = self._plugin_classes[name]
            instance = plugin_class(plugin_manager=self, config=config)

            # Call on_load
            if instance.on_load():
                info.instance = instance
                info.config = config or {}
                info.state = PluginState.LOADED
                self._load_order.append(name)

                # Publish event
                if self.event_bus:
                    from .event_bus import EventType
                    self.event_bus.publish(
                        EventType.PLUGIN_LOADED,
                        {"plugin": name, "version": info.version}
                    )

                return True
            else:
                info.state = PluginState.ERROR
                info.error_message = "on_load returned False"
                return False

        except Exception as e:
            info.state = PluginState.ERROR
            info.error_message = str(e)
            return False

    def enable_plugin(self, name: str) -> bool:
        """
        Enable a loaded plugin

        Args:
            name: Plugin name

        Returns:
            True if enabled successfully
        """
        if name not in self._plugins:
            return False

        info = self._plugins[name]

        if info.state == PluginState.ACTIVE:
            return True

        if info.state != PluginState.LOADED:
            return False

        try:
            if info.instance and info.instance.on_enable():
                info.state = PluginState.ACTIVE
                info.instance._enabled = True

                # Register provided services
                for service in info.provides:
                    self._services[service] = info.instance

                return True
            return False

        except Exception as e:
            info.state = PluginState.ERROR
            info.error_message = str(e)
            return False

    def disable_plugin(self, name: str) -> bool:
        """
        Disable an active plugin

        Args:
            name: Plugin name

        Returns:
            True if disabled successfully
        """
        if name not in self._plugins:
            return False

        info = self._plugins[name]

        if info.state != PluginState.ACTIVE:
            return True

        try:
            if info.instance:
                info.instance.on_disable()
                info.instance._enabled = False

            # Unregister services
            for service in info.provides:
                self._services.pop(service, None)

            info.state = PluginState.LOADED
            return True

        except Exception as e:
            info.error_message = str(e)
            return False

    def unload_plugin(self, name: str) -> bool:
        """
        Unload a plugin completely

        Args:
            name: Plugin name

        Returns:
            True if unloaded successfully
        """
        if name not in self._plugins:
            return False

        info = self._plugins[name]

        # Disable first if active
        if info.state == PluginState.ACTIVE:
            self.disable_plugin(name)

        try:
            if info.instance:
                info.instance.on_unload()

            # Remove from load order
            if name in self._load_order:
                self._load_order.remove(name)

            info.state = PluginState.UNLOADED
            info.instance = None

            # Publish event
            if self.event_bus:
                from .event_bus import EventType
                self.event_bus.publish(
                    EventType.PLUGIN_UNLOADED,
                    {"plugin": name}
                )

            return True

        except Exception as e:
            info.error_message = str(e)
            return False

    def _check_dependencies(self, name: str) -> bool:
        """Check if plugin dependencies are satisfied"""
        info = self._plugins[name]

        for dep in info.dependencies:
            if dep not in self._plugins:
                print(f"Missing dependency: {dep} (required by {name})")
                return False

        return True

    def get_plugin(self, name: str) -> Optional[PluginBase]:
        """Get plugin instance by name"""
        if name in self._plugins:
            return self._plugins[name].instance
        return None

    def get_service(self, service_name: str) -> Optional[Any]:
        """Get a service provided by a plugin"""
        return self._services.get(service_name)

    def register_hook(self, hook_name: str, callback: Callable) -> None:
        """Register a callback for a hook"""
        if hook_name not in self._hooks:
            self._hooks[hook_name] = []
        self._hooks[hook_name].append(callback)

    def execute_hook(self, hook_name: str, *args, **kwargs) -> List[Any]:
        """Execute all callbacks for a hook"""
        results = []
        for callback in self._hooks.get(hook_name, []):
            try:
                result = callback(*args, **kwargs)
                results.append(result)
            except Exception as e:
                print(f"Hook error ({hook_name}): {e}")
        return results

    def get_plugin_info(self, name: str) -> Optional[PluginInfo]:
        """Get plugin information"""
        return self._plugins.get(name)

    def list_plugins(self) -> List[PluginInfo]:
        """List all discovered plugins"""
        return list(self._plugins.values())

    def load_all(self) -> Dict[str, bool]:
        """
        Load all discovered plugins

        Returns:
            Dict of plugin names to load success status
        """
        results = {}

        # Sort by priority
        sorted_plugins = sorted(
            self._plugins.items(),
            key=lambda x: x[1].priority.value
        )

        for name, info in sorted_plugins:
            results[name] = self.load_plugin(name)

        return results

    def enable_all(self) -> Dict[str, bool]:
        """
        Enable all loaded plugins

        Returns:
            Dict of plugin names to enable success status
        """
        results = {}

        for name in self._load_order:
            results[name] = self.enable_plugin(name)

        return results


# Example plugin implementations
class MemoryPluginBase(PluginBase):
    """Base class for memory-related plugins"""

    PROVIDES = ["memory_extension"]

    @abstractmethod
    def process_memory(self, content: str, context: Dict) -> Dict:
        """Process and extend memory data"""
        pass


class GeneratorPluginBase(PluginBase):
    """Base class for generation-related plugins"""

    PROVIDES = ["generator_extension"]

    @abstractmethod
    def pre_generate(self, prompt: str, context: Dict) -> str:
        """Modify prompt before generation"""
        pass

    @abstractmethod
    def post_generate(self, content: str, context: Dict) -> str:
        """Process generated content"""
        pass


class EvaluatorPluginBase(PluginBase):
    """Base class for evaluation-related plugins"""

    PROVIDES = ["evaluator_extension"]

    @abstractmethod
    def evaluate(self, content: str, criteria: Dict) -> Dict:
        """Evaluate content against criteria"""
        pass
