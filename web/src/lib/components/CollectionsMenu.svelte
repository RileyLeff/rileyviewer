<script lang="ts">
	import { getCollections, addCollection, removeCollection, type Collection } from '$lib/collections.svelte';

	interface Props {
		activeTag: string | null;
		searchQuery: string;
		onselectcollection: (c: { tag?: string; search?: string; plotIds?: string[] }) => void;
	}

	let { activeTag, searchQuery, onselectcollection }: Props = $props();

	let open = $state(false);
	let saving = $state(false);
	let saveName = $state('');

	let collections = $derived(getCollections());

	let canSave = $derived(activeTag !== null || searchQuery.length > 0);

	function handleClickOutside(e: MouseEvent) {
		const target = e.target as HTMLElement;
		if (!target.closest('.collections-menu')) {
			close();
		}
	}

	function close() {
		open = false;
		saving = false;
		saveName = '';
	}

	function handleSelect(c: Collection) {
		onselectcollection({ tag: c.tag, search: c.search, plotIds: c.plotIds });
		close();
	}

	function handleDelete(e: MouseEvent, id: string) {
		e.stopPropagation();
		removeCollection(id);
	}

	function startSaving() {
		saving = true;
		saveName = '';
	}

	function commitSave() {
		const name = saveName.trim();
		if (!name) return;
		addCollection({
			name,
			tag: activeTag ?? undefined,
			search: searchQuery || undefined,
		});
		saving = false;
		saveName = '';
	}

	function handleSaveKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			commitSave();
		} else if (e.key === 'Escape') {
			saving = false;
			saveName = '';
		}
	}
</script>

<svelte:window
	onclick={open ? handleClickOutside : undefined}
	onkeydown={open ? (e) => { if (e.key === 'Escape') close(); } : undefined}
/>

<div class="relative collections-menu">
	<button
		class="border border-[var(--color-border)] px-2 py-0.5 text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-text)] transition-colors"
		onclick={(e) => { e.stopPropagation(); open = !open; saving = false; saveName = ''; }}
	>[collections]</button>

	{#if open}
		<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
		<div
			class="absolute right-0 top-full mt-1 z-50 border border-[var(--color-border)] bg-[var(--color-bg-raised)] p-3 min-w-[220px]"
			onclick={(e) => e.stopPropagation()}
		>
			{#if collections.length > 0}
				<div class="text-[11px] text-[var(--color-text-faint)] uppercase tracking-wider mb-1.5">saved</div>
				<div class="flex flex-col gap-0.5 mb-3">
					{#each collections as c (c.id)}
						<div class="flex items-center gap-1 group">
							<button
								class="flex-1 text-left text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] py-0.5 transition-colors truncate"
								onclick={() => handleSelect(c)}
							>{c.name}</button>
							<button
								class="text-[10px] text-[var(--color-text-faint)] hover:text-[var(--color-text)] opacity-0 group-hover:opacity-100 transition-opacity px-1"
								onclick={(e) => handleDelete(e, c.id)}
							>[x]</button>
						</div>
					{/each}
				</div>
			{:else}
				<div class="text-[11px] text-[var(--color-text-faint)] mb-3">no saved collections</div>
			{/if}

			{#if !saving}
				<button
					class="text-xs border border-[var(--color-border)] text-[var(--color-text-muted)] px-2 py-0.5 transition-colors {canSave ? 'hover:border-[var(--color-accent)] hover:text-[var(--color-text)]' : 'opacity-40 cursor-not-allowed'}"
					onclick={startSaving}
					disabled={!canSave}
				>[save current filter]</button>
				{#if !canSave}
					<div class="text-[10px] text-[var(--color-text-faint)] mt-1">set a tag or search first</div>
				{/if}
			{:else}
				<div class="text-[11px] text-[var(--color-text-faint)] uppercase tracking-wider mb-1.5">name</div>
				<div class="flex gap-1">
					<input
						type="text"
						bind:value={saveName}
						onkeydown={handleSaveKeydown}
						placeholder="collection name"
						class="flex-1 min-w-0 border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] text-xs px-1.5 py-0.5 placeholder:text-[var(--color-text-faint)] focus:border-[var(--color-accent)] focus:outline-none"
					/>
					<button
						class="text-xs border border-[var(--color-accent)] text-[var(--color-accent)] px-2 py-0.5 hover:bg-[var(--color-accent-muted)] transition-colors disabled:opacity-40"
						onclick={commitSave}
						disabled={saveName.trim().length === 0}
					>[ok]</button>
				</div>
			{/if}
		</div>
	{/if}
</div>
