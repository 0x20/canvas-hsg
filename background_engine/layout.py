"""
Layout Engine and Component System

Core layout engine that handles positioning, sizing, and spacing of components
in a flexible, configurable way.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
from PIL import Image, ImageDraw
import logging

from .config import BackgroundConfig


@dataclass
class ComponentLayout:
    """Calculated layout information for a component"""
    x: int
    y: int
    width: int
    height: int
    component_id: str
    spacing_before: float
    spacing_after: float


class LayoutComponent(ABC):
    """
    Base class for all background components.
    
    Each component knows how to calculate its own size and render itself
    at a given position.
    """
    
    def __init__(self, component_id: str = None):
        self.component_id = component_id or self.__class__.__name__
    
    @abstractmethod
    def calculate_size(self, canvas_width: int, canvas_height: int, 
                      config: BackgroundConfig) -> Tuple[int, int]:
        """
        Calculate the required size for this component.
        
        Args:
            canvas_width: Canvas width in pixels
            canvas_height: Canvas height in pixels  
            config: Background configuration
            
        Returns:
            Tuple of (width, height) in pixels
        """
        pass
    
    @abstractmethod
    def render(self, draw: ImageDraw.Draw, x: int, y: int, width: int, height: int,
               canvas_width: int, canvas_height: int, config: BackgroundConfig) -> None:
        """
        Render this component at the specified position and size.
        
        Args:
            draw: PIL ImageDraw context
            x, y: Top-left position
            width, height: Allocated size
            canvas_width, canvas_height: Full canvas dimensions
            config: Background configuration
        """
        pass
    
    def get_min_size(self, canvas_width: int, canvas_height: int, 
                    config: BackgroundConfig) -> Tuple[int, int]:
        """
        Get minimum size requirements. Default implementation uses calculate_size.
        Override if component has specific minimum size requirements.
        """
        return self.calculate_size(canvas_width, canvas_height, config)
    
    def get_max_size(self, canvas_width: int, canvas_height: int,
                    config: BackgroundConfig) -> Tuple[int, int]:
        """
        Get maximum size constraints. Default implementation has no max.
        Override if component should be constrained.
        """
        return canvas_width, canvas_height


class LayoutEngine:
    """
    Layout engine that positions and sizes components based on configuration.
    
    Supports various layout algorithms and handles spacing, centering,
    and overflow management.
    """
    
    def __init__(self, canvas_width: int, canvas_height: int, config: BackgroundConfig):
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.config = config
        self.components: List[Dict[str, Any]] = []
        
        # Calculate usable area (accounting for padding)
        padding_x = int(canvas_width * config.canvas_padding)
        padding_y = int(canvas_height * config.canvas_padding)
        
        self.content_x = padding_x
        self.content_y = padding_y
        self.content_width = canvas_width - 2 * padding_x
        self.content_height = canvas_height - 2 * padding_y
        
    def add_component(self, component: LayoutComponent, 
                     spacing_before: Optional[float] = None,
                     spacing_after: Optional[float] = None) -> None:
        """
        Add a component to the layout.
        
        Args:
            component: Component to add
            spacing_before: Spacing before this component (as percentage of canvas height)
            spacing_after: Spacing after this component (as percentage of canvas height)
        """
        # Use default spacing if not specified
        if spacing_before is None:
            spacing_before = self.config.default_component_spacing
        if spacing_after is None:
            spacing_after = self.config.default_component_spacing
            
        self.components.append({
            'component': component,
            'spacing_before': spacing_before,
            'spacing_after': spacing_after
        })
    
    def calculate_layout(self) -> List[ComponentLayout]:
        """
        Calculate layout for all components.
        
        Returns:
            List of ComponentLayout objects with calculated positions and sizes
        """
        if not self.components:
            return []
        
        # Calculate all component sizes first
        component_info = []
        total_content_height = 0
        
        for comp_data in self.components:
            component = comp_data['component']
            spacing_before = comp_data['spacing_before']
            spacing_after = comp_data['spacing_after']
            
            # Calculate component size
            comp_width, comp_height = component.calculate_size(
                self.canvas_width, self.canvas_height, self.config
            )
            
            # Apply size constraints
            min_width, min_height = component.get_min_size(
                self.canvas_width, self.canvas_height, self.config
            )
            max_width, max_height = component.get_max_size(
                self.canvas_width, self.canvas_height, self.config
            )
            
            # Constrain to content area and component limits
            comp_width = min(max(comp_width, min_width), 
                           min(max_width, self.content_width))
            comp_height = min(max(comp_height, min_height), 
                            min(max_height, self.content_height))
            
            # Convert spacing to pixels
            spacing_before_px = int(spacing_before * self.canvas_height)
            spacing_after_px = int(spacing_after * self.canvas_height)
            
            component_info.append({
                'component': component,
                'width': comp_width,
                'height': comp_height,
                'spacing_before': spacing_before,
                'spacing_after': spacing_after,
                'spacing_before_px': spacing_before_px,
                'spacing_after_px': spacing_after_px
            })
            
            total_content_height += spacing_before_px + comp_height + spacing_after_px
        
        # Calculate layout based on algorithm
        if self.config.layout_algorithm == "vertical_flow":
            return self._calculate_vertical_flow_layout(component_info, total_content_height)
        elif self.config.layout_algorithm == "golden_ratio":
            return self._calculate_golden_ratio_layout(component_info)
        elif self.config.layout_algorithm == "rule_of_thirds":
            return self._calculate_rule_of_thirds_layout(component_info)
        else:
            # Default to vertical flow
            return self._calculate_vertical_flow_layout(component_info, total_content_height)
    
    def _calculate_vertical_flow_layout(self, component_info: List[Dict], 
                                      total_content_height: int) -> List[ComponentLayout]:
        """Calculate layout using vertical flow algorithm"""
        layouts = []
        
        # Determine starting Y position based on vertical alignment
        if self.config.vertical_alignment == "top":
            current_y = self.content_y
        elif self.config.vertical_alignment == "center":
            current_y = self.content_y + (self.content_height - total_content_height) // 2
        elif self.config.vertical_alignment == "bottom":
            current_y = self.content_y + self.content_height - total_content_height
        else:  # "distribute"
            current_y = self.content_y
            # Adjust spacing to distribute components evenly
            if len(component_info) > 1:
                extra_space = self.content_height - total_content_height
                extra_spacing_per_gap = extra_space // (len(component_info) - 1)
            else:
                extra_spacing_per_gap = 0
        
        for i, info in enumerate(component_info):
            component = info['component']
            comp_width = info['width']
            comp_height = info['height']
            spacing_before_px = info['spacing_before_px']
            spacing_after_px = info['spacing_after_px']
            
            # Add spacing before
            current_y += spacing_before_px
            
            # Add extra spacing for distribution (except for first component)
            if self.config.vertical_alignment == "distribute" and i > 0:
                current_y += extra_spacing_per_gap
            
            # Calculate X position (center horizontally if enabled)
            if self.config.center_horizontally:
                comp_x = self.content_x + (self.content_width - comp_width) // 2
            else:
                comp_x = self.content_x
            
            # Create layout
            layout = ComponentLayout(
                x=comp_x,
                y=current_y,
                width=comp_width,
                height=comp_height,
                component_id=component.component_id,
                spacing_before=info['spacing_before'],
                spacing_after=info['spacing_after']
            )
            layouts.append(layout)
            
            # Move to next position
            current_y += comp_height + spacing_after_px
        
        return layouts
    
    def _calculate_golden_ratio_layout(self, component_info: List[Dict]) -> List[ComponentLayout]:
        """Calculate layout using golden ratio positioning"""
        # Golden ratio points
        golden_upper = int(self.canvas_height * 0.382)  # 1 - 1/φ
        golden_lower = int(self.canvas_height * 0.618)  # 1/φ
        
        layouts = []
        
        # Simple implementation: place first component at golden upper,
        # last component at golden lower, distribute others
        if len(component_info) == 1:
            info = component_info[0]
            comp_x = self.content_x + (self.content_width - info['width']) // 2
            comp_y = golden_upper - info['height'] // 2
            
            layout = ComponentLayout(
                x=comp_x, y=comp_y,
                width=info['width'], height=info['height'],
                component_id=info['component'].component_id,
                spacing_before=info['spacing_before'],
                spacing_after=info['spacing_after']
            )
            layouts.append(layout)
        
        elif len(component_info) >= 2:
            # Place first at golden upper
            info = component_info[0]
            comp_x = self.content_x + (self.content_width - info['width']) // 2
            comp_y = max(self.content_y, golden_upper - info['height'] // 2)
            
            layout = ComponentLayout(
                x=comp_x, y=comp_y,
                width=info['width'], height=info['height'],
                component_id=info['component'].component_id,
                spacing_before=info['spacing_before'],
                spacing_after=info['spacing_after']
            )
            layouts.append(layout)
            
            # Place last at golden lower
            info = component_info[-1]
            comp_x = self.content_x + (self.content_width - info['width']) // 2
            comp_y = min(self.content_y + self.content_height - info['height'],
                        golden_lower - info['height'] // 2)
            
            layout = ComponentLayout(
                x=comp_x, y=comp_y,
                width=info['width'], height=info['height'],
                component_id=info['component'].component_id,
                spacing_before=info['spacing_before'],
                spacing_after=info['spacing_after']
            )
            layouts.append(layout)
            
            # Distribute middle components evenly
            if len(component_info) > 2:
                start_y = layouts[0].y + layouts[0].height
                end_y = layouts[-1].y
                available_height = end_y - start_y
                
                for i, info in enumerate(component_info[1:-1], 1):
                    ratio = i / (len(component_info) - 1)
                    comp_x = self.content_x + (self.content_width - info['width']) // 2
                    comp_y = int(start_y + available_height * ratio - info['height'] // 2)
                    
                    layout = ComponentLayout(
                        x=comp_x, y=comp_y,
                        width=info['width'], height=info['height'],
                        component_id=info['component'].component_id,
                        spacing_before=info['spacing_before'],
                        spacing_after=info['spacing_after']
                    )
                    layouts.insert(-1, layout)  # Insert before last element
        
        return layouts
    
    def _calculate_rule_of_thirds_layout(self, component_info: List[Dict]) -> List[ComponentLayout]:
        """Calculate layout using rule of thirds positioning"""
        # Rule of thirds lines
        third_upper = self.canvas_height // 3
        third_lower = 2 * self.canvas_height // 3
        
        layouts = []
        
        # Simple implementation: distribute components at third lines
        if len(component_info) == 1:
            info = component_info[0]
            comp_x = self.content_x + (self.content_width - info['width']) // 2
            comp_y = third_upper - info['height'] // 2
            
            layout = ComponentLayout(
                x=comp_x, y=comp_y,
                width=info['width'], height=info['height'],
                component_id=info['component'].component_id,
                spacing_before=info['spacing_before'],
                spacing_after=info['spacing_after']
            )
            layouts.append(layout)
        
        else:
            # Distribute components across the three sections
            section_height = self.content_height // 3
            
            for i, info in enumerate(component_info):
                section = i % 3
                section_y = self.content_y + section * section_height
                section_center_y = section_y + section_height // 2
                
                comp_x = self.content_x + (self.content_width - info['width']) // 2
                comp_y = section_center_y - info['height'] // 2
                
                layout = ComponentLayout(
                    x=comp_x, y=comp_y,
                    width=info['width'], height=info['height'],
                    component_id=info['component'].component_id,
                    spacing_before=info['spacing_before'],
                    spacing_after=info['spacing_after']
                )
                layouts.append(layout)
        
        return layouts
    
    def render(self, background_color: Optional[Tuple[int, int, int]] = None) -> Image.Image:
        """
        Render all components to an image.
        
        Args:
            background_color: Background color override
            
        Returns:
            PIL Image with rendered components
        """
        bg_color = background_color or self.config.background_color
        img = Image.new('RGB', (self.canvas_width, self.canvas_height), bg_color)
        draw = ImageDraw.Draw(img)
        
        layouts = self.calculate_layout()
        
        for layout in layouts:
            # Find the corresponding component
            component = None
            for comp_data in self.components:
                if comp_data['component'].component_id == layout.component_id:
                    component = comp_data['component']
                    break
            
            if component:
                try:
                    component.render(
                        draw, layout.x, layout.y, layout.width, layout.height,
                        self.canvas_width, self.canvas_height, self.config
                    )
                except Exception as e:
                    logging.error(f"Error rendering component {component.component_id}: {e}")
        
        return img
    
    def get_layout_info(self) -> Dict[str, Any]:
        """Get detailed layout information for debugging"""
        layouts = self.calculate_layout()
        
        return {
            'canvas_size': (self.canvas_width, self.canvas_height),
            'content_area': {
                'x': self.content_x, 'y': self.content_y,
                'width': self.content_width, 'height': self.content_height
            },
            'algorithm': self.config.layout_algorithm,
            'components': [
                {
                    'id': layout.component_id,
                    'position': (layout.x, layout.y),
                    'size': (layout.width, layout.height),
                    'spacing': {
                        'before': layout.spacing_before,
                        'after': layout.spacing_after
                    }
                }
                for layout in layouts
            ]
        }