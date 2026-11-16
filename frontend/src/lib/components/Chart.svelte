<script lang="ts">
  // Type-only: erased at build time, so it pulls nothing into the bundle.
  import type { ECharts, EChartsCoreOption } from 'echarts/core';

  interface Props {
    /** Built by the caller, which is also where the theme tokens are read. */
    option: EChartsCoreOption;
    height: number;
    /** A canvas has no text for a screen reader, so the caller supplies it. */
    ariaLabel: string;
  }

  let { option, height, ariaLabel }: Props = $props();

  let container: HTMLDivElement;
  let chart = $state<ECharts | undefined>();

  $effect(() => {
    let live = true;
    let observer: ResizeObserver | undefined;

    // Loaded on demand: ECharts is by far the largest dependency and only this
    // component needs it. lib/echarts.ts holds the narrow static imports so
    // the bundler can tree-shake them into one small lazy chunk.
    void (async () => {
      const { init } = await import('$lib/echarts');
      if (!live) return;

      const instance = init(container);
      // The sidebar collapses and the window resizes; a canvas does not reflow.
      observer = new ResizeObserver(() => instance.resize());
      observer.observe(container);

      chart = instance;
    })();

    return () => {
      live = false;
      observer?.disconnect();
      chart?.dispose();
      chart = undefined;
    };
  });

  // Runs once the chart exists, and again whenever the caller rebuilds the
  // option — which includes every theme switch.
  $effect(() => {
    // notMerge: a chart with fewer bars than last time must drop the old ones.
    chart?.setOption(option, { notMerge: true });
  });
</script>

<div
  bind:this={container}
  class="chart"
  style:height="{height}px"
  role="img"
  aria-label={ariaLabel}
></div>

<style>
  .chart {
    width: 100%;
  }
</style>
