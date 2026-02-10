<script lang="ts">
	import {
		getTheme, setTheme, type ThemePreference,
		getBackground, setBackground, type BackgroundMode,
		getLinkLogo, setLinkLogo,
		getThumbPos, setThumbPos, type ThumbnailPosition
	} from '$lib/theme.svelte';

	let open = $state(false);

	let theme = $derived(getTheme());
	let bg = $derived(getBackground());
	let link = $derived(getLinkLogo());
	let thumbPos = $derived(getThumbPos());

	const themeOptions: { value: ThemePreference; label: string }[] = [
		{ value: 'light', label: 'light' },
		{ value: 'dark', label: 'dark' },
		{ value: 'system', label: 'auto' }
	];

	const bgOptions: { value: BackgroundMode; label: string }[] = [
		{ value: 'sticker', label: 'sticker' },
		{ value: 'blank', label: 'blank' },
		{ value: 'mania', label: 'mania' }
	];

	const thumbOptions: { value: ThumbnailPosition; label: string }[] = [
		{ value: 'bottom', label: 'bottom' },
		{ value: 'top', label: 'top' },
		{ value: 'left', label: 'left' },
		{ value: 'right', label: 'right' }
	];

	function handleClickOutside(e: MouseEvent) {
		const target = e.target as HTMLElement;
		if (!target.closest('.settings-menu')) {
			open = false;
		}
	}
</script>

<svelte:window
	onclick={open ? handleClickOutside : undefined}
	onkeydown={open ? (e) => { if (e.key === 'Escape') open = false; } : undefined}
/>

<div class="relative settings-menu">
	<button
		class="border border-[var(--color-border)] px-2 py-0.5 text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-text)] transition-colors"
		onclick={(e) => { e.stopPropagation(); open = !open; }}
	>[settings]</button>

	{#if open}
		<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
		<div
			class="absolute right-0 top-full mt-1 z-50 border border-[var(--color-border)] bg-[var(--color-bg-raised)] p-3 min-w-[200px]"
			onclick={(e) => e.stopPropagation()}
		>
			<div class="text-[11px] text-[var(--color-text-faint)] uppercase tracking-wider mb-1.5">theme</div>
			<div class="flex gap-1 mb-3">
				{#each themeOptions as opt (opt.value)}
					<button
						class={`border px-2 py-0.5 text-xs transition-colors ${
							theme === opt.value
								? 'border-[var(--color-accent)] text-[var(--color-accent)]'
								: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-text-faint)]'
						}`}
						onclick={() => setTheme(opt.value)}
					>[{opt.label}]</button>
				{/each}
			</div>

			<div class="text-[11px] text-[var(--color-text-faint)] uppercase tracking-wider mb-1.5">background</div>
			<div class="flex gap-1 mb-3">
				{#each bgOptions as opt (opt.value)}
					<button
						class={`border px-2 py-0.5 text-xs transition-colors ${
							bg === opt.value
								? 'border-[var(--color-accent)] text-[var(--color-accent)]'
								: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-text-faint)]'
						}`}
						onclick={() => setBackground(opt.value)}
					>[{opt.label}]</button>
				{/each}
			</div>

			<div class="text-[11px] text-[var(--color-text-faint)] uppercase tracking-wider mb-1.5">thumbnails</div>
			<div class="flex gap-1 mb-3">
				{#each thumbOptions as opt (opt.value)}
					<button
						class={`border px-2 py-0.5 text-xs transition-colors ${
							thumbPos === opt.value
								? 'border-[var(--color-accent)] text-[var(--color-accent)]'
								: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-text-faint)]'
						}`}
						onclick={() => setThumbPos(opt.value)}
					>[{opt.label}]</button>
				{/each}
			</div>

			<div class="text-[11px] text-[var(--color-text-faint)] uppercase tracking-wider mb-1.5">sticker link</div>
			<button
				class={`border px-2 py-0.5 text-xs transition-colors ${
					link
						? 'border-[var(--color-accent)] text-[var(--color-accent)]'
						: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-text-faint)]'
				}`}
				onclick={() => setLinkLogo(!link)}
			>[{link ? 'on' : 'off'}]</button>
			{#if link}
				<span class="text-[10px] text-[var(--color-text-faint)] ml-1.5">stickermule</span>
			{/if}
		</div>
	{/if}
</div>
