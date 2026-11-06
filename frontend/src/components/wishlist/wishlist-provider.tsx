"use client";

import {
  createContext,
  type ReactNode,
  use,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";
import type { AccountApi } from "@/lib/account/client";

type WishlistApi = Pick<AccountApi, "wishlistMembership" | "saveWishlist" | "removeWishlist">;

type WishlistContextValue = {
  register: (productId: string) => void;
  isSaved: (productId: string) => boolean;
  isPending: (productId: string) => boolean;
  authenticated: boolean;
  toggle: (productId: string) => Promise<boolean | null>;
};

type PrincipalState<T> = { principalId: string | null; value: T };

const EMPTY_MEMBERSHIPS: Record<string, boolean> = {};
const EMPTY_PENDING = new Set<string>();

const WishlistContext = createContext<WishlistContextValue | null>(null);

export function WishlistProvider({
  children,
  locale,
  api,
}: {
  children: ReactNode;
  locale: AppLocale;
  api?: WishlistApi;
}) {
  const { session, sessionStatus } = useCommerce();
  const principalId =
    sessionStatus === "ready" && session?.authenticated && session.user ? session.user.id : null;
  const authenticated = principalId !== null;
  const [membershipState, setMembershipState] = useState<PrincipalState<Record<string, boolean>>>({
    principalId: null,
    value: {},
  });
  const [pendingState, setPendingState] = useState<PrincipalState<Set<string>>>({
    principalId: null,
    value: new Set(),
  });
  const memberships =
    membershipState.principalId === principalId ? membershipState.value : EMPTY_MEMBERSHIPS;
  const pending = pendingState.principalId === principalId ? pendingState.value : EMPTY_PENDING;
  const principalRef = useRef(principalId);
  const registered = useRef(new Set<string>());
  const queued = useRef(new Set<string>());
  const timer = useRef<number | null>(null);
  const resolveApi = useCallback(
    () =>
      api
        ? Promise.resolve(api)
        : import("@/lib/account/client").then(({ accountApi }) => accountApi),
    [api],
  );

  useEffect(() => {
    principalRef.current = principalId;
  }, [principalId]);

  const flush = useCallback(() => {
    if (!principalId || !queued.current.size) return;
    const requestedPrincipal = principalId;
    const ids = [...queued.current];
    queued.current.clear();
    const batches = Array.from({ length: Math.ceil(ids.length / 50) }, (_, index) =>
      ids.slice(index * 50, (index + 1) * 50),
    );
    void resolveApi()
      .then((client) => Promise.all(batches.map((batch) => client.wishlistMembership(batch))))
      .then((responses) => {
        if (principalRef.current !== requestedPrincipal) return;
        setMembershipState((current) => ({
          principalId: requestedPrincipal,
          value: {
            ...(current.principalId === requestedPrincipal ? current.value : {}),
            ...Object.fromEntries(
              responses
                .flatMap((response) => response.items)
                .map((item) => [item.product_id, item.saved]),
            ),
          },
        }));
      })
      .catch(() => undefined);
  }, [principalId, resolveApi]);

  const register = useCallback(
    (productId: string) => {
      registered.current.add(productId);
      if (!principalId || productId in memberships) return;
      queued.current.add(productId);
      if (timer.current !== null) return;
      timer.current = window.setTimeout(() => {
        timer.current = null;
        flush();
      }, 25);
    },
    [flush, memberships, principalId],
  );

  useEffect(() => {
    if (!principalId) {
      queued.current.clear();
      return;
    }
    registered.current.forEach((id) => queued.current.add(id));
    flush();
  }, [flush, principalId]);

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );

  const toggle = useCallback(
    async (productId: string) => {
      if (!principalId) return null;
      const requestedPrincipal = principalId;
      const wasSaved = Boolean(memberships[productId]);
      const nextSaved = !wasSaved;
      setMembershipState((current) => ({
        principalId: requestedPrincipal,
        value: {
          ...(current.principalId === requestedPrincipal ? current.value : {}),
          [productId]: nextSaved,
        },
      }));
      setPendingState((current) => ({
        principalId: requestedPrincipal,
        value: new Set(current.principalId === requestedPrincipal ? current.value : []).add(
          productId,
        ),
      }));
      try {
        const client = await resolveApi();
        if (nextSaved) await client.saveWishlist(productId, locale);
        else await client.removeWishlist(productId);
        return nextSaved;
      } catch (error) {
        if (principalRef.current === requestedPrincipal) {
          setMembershipState((current) => ({
            principalId: requestedPrincipal,
            value: {
              ...(current.principalId === requestedPrincipal ? current.value : {}),
              [productId]: wasSaved,
            },
          }));
        }
        throw error;
      } finally {
        if (principalRef.current === requestedPrincipal) {
          setPendingState((current) => {
            const next = new Set(current.principalId === requestedPrincipal ? current.value : []);
            next.delete(productId);
            return { principalId: requestedPrincipal, value: next };
          });
        }
      }
    },
    [locale, memberships, principalId, resolveApi],
  );

  return (
    <WishlistContext
      value={{
        authenticated,
        register,
        isSaved: (productId) => Boolean(memberships[productId]),
        isPending: (productId) => pending.has(productId),
        toggle,
      }}
    >
      {children}
    </WishlistContext>
  );
}

export function useWishlistMembership() {
  return (
    use(WishlistContext) ?? {
      authenticated: false,
      register: () => undefined,
      isSaved: () => false,
      isPending: () => false,
      toggle: async () => null,
    }
  );
}
