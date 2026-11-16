/**
 * The only ECharts the application registers.
 *
 * Two things have to be true at once: the library must not be in the main
 * bundle, and only the bar chart must be pulled in. Static named imports are
 * what lets the bundler tree-shake — a dynamic `import('echarts/charts')`
 * would need the whole namespace at runtime and drag in every chart type,
 * including the map code and its GeoJSON parser.
 *
 * So the narrow imports live here, and Chart.svelte loads *this module*
 * dynamically. The result is one small lazy chunk.
 */

import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { init, use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

export { init };
