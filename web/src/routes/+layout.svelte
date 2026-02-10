<script lang="ts">
	import './layout.css';
	import { onMount } from 'svelte';
	import { initSystemListener } from '$lib/theme.svelte';
	import favicon from '$lib/assets/riley_logo.svg';

	let { children } = $props();

	onMount(() => {
		return initSystemListener();
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

{@render children()}
