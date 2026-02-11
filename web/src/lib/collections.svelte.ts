import { browser } from '$app/environment';

const STORAGE_KEY = 'rileyviewer-collections';

export type Collection = {
	id: string;
	name: string;
	tag?: string;
	search?: string;
	plotIds?: string[];
	createdAt: number;
};

function loadCollections(): Collection[] {
	if (!browser) return [];
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		return raw ? JSON.parse(raw) : [];
	} catch {
		return [];
	}
}

function persist(items: Collection[]) {
	if (browser) {
		localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
	}
}

let collections = $state<Collection[]>(loadCollections());

export function getCollections(): Collection[] {
	return collections;
}

export function addCollection(c: Omit<Collection, 'id' | 'createdAt'>): Collection {
	const item: Collection = {
		...c,
		id: crypto.randomUUID(),
		createdAt: Date.now(),
	};
	collections.push(item);
	persist(collections);
	return item;
}

export function removeCollection(id: string) {
	const idx = collections.findIndex((c) => c.id === id);
	if (idx >= 0) {
		collections.splice(idx, 1);
		persist(collections);
	}
}
