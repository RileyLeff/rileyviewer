<script lang="ts">
	import type { PlotMessage } from '$lib/types';

	interface Props {
		plot: PlotMessage;
		onupdate: (id: string, fields: { title?: string | null; notes?: string | null; tags?: string[] }) => void;
		requestEdit?: 'title' | 'tags' | 'notes' | null;
		oneditrequesthandled?: () => void;
	}

	let { plot, onupdate, requestEdit = null, oneditrequesthandled }: Props = $props();

	let editingTitle = $state(false);
	let editingTags = $state(false);
	let editingNotes = $state(false);

	$effect(() => {
		if (requestEdit === 'title') { startEditTitle(); oneditrequesthandled?.(); }
		else if (requestEdit === 'tags') { startEditTags(); oneditrequesthandled?.(); }
		else if (requestEdit === 'notes') { startEditNotes(); oneditrequesthandled?.(); }
	});

	let titleDraft = $state('');
	let tagsDraft = $state('');
	let notesDraft = $state('');

	function startEditTitle() {
		titleDraft = plot.title ?? '';
		editingTitle = true;
	}

	function saveTitle() {
		editingTitle = false;
		const trimmed = titleDraft.trim();
		const newVal = trimmed === '' ? null : trimmed;
		const oldVal = plot.title ?? null;
		if (newVal !== oldVal) {
			onupdate(plot.id, { title: newVal });
		}
	}

	function startEditTags() {
		tagsDraft = (plot.tags ?? []).join(', ');
		editingTags = true;
	}

	function saveTags() {
		editingTags = false;
		const parsed = tagsDraft
			.split(',')
			.map((t) => t.trim())
			.filter((t) => t.length > 0);
		const oldTags = plot.tags ?? [];
		if (parsed.length !== oldTags.length || parsed.some((t, i) => t !== oldTags[i])) {
			onupdate(plot.id, { tags: parsed });
		}
	}

	function startEditNotes() {
		notesDraft = plot.notes ?? '';
		editingNotes = true;
	}

	function saveNotes() {
		editingNotes = false;
		const trimmed = notesDraft.trim();
		const newVal = trimmed === '' ? null : trimmed;
		const oldVal = plot.notes ?? null;
		if (newVal !== oldVal) {
			onupdate(plot.id, { notes: newVal });
		}
	}

	function handleTitleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			(e.currentTarget as HTMLInputElement).blur();
		} else if (e.key === 'Escape') {
			editingTitle = false;
		}
	}

	function handleTagsKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			(e.currentTarget as HTMLInputElement).blur();
		} else if (e.key === 'Escape') {
			editingTags = false;
		}
	}

	function handleNotesKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			(e.currentTarget as HTMLTextAreaElement).blur();
		} else if (e.key === 'Escape') {
			editingNotes = false;
		}
	}

	function focusOnMount(node: HTMLElement) {
		node.focus();
	}
</script>

<div class="flex items-center gap-3 border-b border-[var(--color-border)] bg-[var(--color-bg-raised)] px-3 py-1 text-xs min-w-0">
	<!-- Title -->
	<div class="flex items-center gap-1 min-w-0 shrink-0 max-w-[40%]">
		{#if editingTitle}
			<input
				type="text"
				bind:value={titleDraft}
				onblur={saveTitle}
				onkeydown={handleTitleKeydown}
				class="w-full min-w-[8rem] border border-[var(--color-accent)] bg-[var(--color-bg)] text-[var(--color-text)] text-xs px-1.5 py-0.5 focus:outline-none"
				use:focusOnMount
			/>
		{:else}
			<button
				class="truncate text-left hover:text-[var(--color-accent)] transition-colors {plot.title ? 'text-[var(--color-text)]' : 'text-[var(--color-text-faint)] italic'}"
				onclick={startEditTitle}
				title="Click to edit title"
			>{plot.title || 'untitled'}</button>
		{/if}
	</div>

	<!-- Tags -->
	<div class="flex items-center gap-1 min-w-0 flex-1">
		{#if editingTags}
			<input
				type="text"
				bind:value={tagsDraft}
				onblur={saveTags}
				onkeydown={handleTagsKeydown}
				placeholder="tag1, tag2, ..."
				class="w-full border border-[var(--color-accent)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-faint)] text-xs px-1.5 py-0.5 focus:outline-none"
				use:focusOnMount
			/>
		{:else if plot.tags && plot.tags.length > 0}
			<button
				class="flex items-center gap-1 flex-wrap min-w-0 hover:text-[var(--color-accent)] transition-colors"
				onclick={startEditTags}
				title="Click to edit tags"
			>
				{#each plot.tags as tag (tag)}
					<span class="border border-[var(--color-border)] text-[var(--color-text-muted)] px-1.5 py-0 leading-tight">{tag}</span>
				{/each}
			</button>
		{:else}
			<button
				class="text-[var(--color-text-faint)] italic hover:text-[var(--color-accent)] transition-colors"
				onclick={startEditTags}
				title="Click to add tags"
			>no tags</button>
		{/if}
	</div>

	<!-- Notes -->
	<div class="flex items-center min-w-0 shrink-0 max-w-[30%] ml-auto">
		{#if editingNotes}
			<textarea
				bind:value={notesDraft}
				onblur={saveNotes}
				onkeydown={handleNotesKeydown}
				rows={1}
				class="w-full min-w-[8rem] border border-[var(--color-accent)] bg-[var(--color-bg)] text-[var(--color-text)] text-xs px-1.5 py-0.5 focus:outline-none resize-none"
				use:focusOnMount
			></textarea>
		{:else}
			<button
				class="truncate text-left hover:text-[var(--color-accent)] transition-colors {plot.notes ? 'text-[var(--color-text-muted)]' : 'text-[var(--color-text-faint)] italic'}"
				onclick={startEditNotes}
				title="Click to edit notes"
			>{plot.notes || 'no notes'}</button>
		{/if}
	</div>
</div>
