"use client";

import {
  createContext,
  type ReactNode,
  use,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type { AppLocale } from "@/i18n/routing";
import {
  ACCESS_REFRESH_WINDOW_MS,
  CommerceClient,
  CommerceError,
  type CommerceApi,
} from "@/lib/commerce/client";
import type {
  CartResponse,
  CheckoutQuoteRequest,
  CheckoutQuoteResponse,
  EmailLogin,
  GeoOption,
  OtpChallenge,
  OtpVerification,
  OrderReceipt,
  PlaceOrderRequest,
  PlaceOrderResponse,
  SessionResponse,
  TrackOrderRequest,
  TrackingResponse,
} from "@/lib/commerce/types";

type PendingAction = "bootstrap" | "cart" | "auth" | "coupon" | "shipping" | "checkout" | null;

type CommerceErrors = {
  session: CommerceError | null;
  cart: CommerceError | null;
  cartMutation: CommerceError | null;
  auth: CommerceError | null;
  checkout: CommerceError | null;
};

type CommerceSnapshot = {
  session: SessionResponse | null;
  cart: CartResponse | null;
};

type CommerceContextValue = CommerceSnapshot & {
  locale: AppLocale;
  csrf: string | null;
  count: number;
  isLoading: boolean;
  isBootstrapping: boolean;
  isReady: boolean;
  isCartMutating: boolean;
  pendingAction: PendingAction;
  errors: CommerceErrors;
  bootstrap: () => Promise<void>;
  refreshCart: () => Promise<CartResponse>;
  addItem: (variantId: string, quantity: number) => Promise<CartResponse>;
  updateItem: (itemId: string, quantity: number) => Promise<CartResponse>;
  removeItem: (itemId: string) => Promise<CartResponse>;
  applyCoupon: (code: string) => Promise<CartResponse>;
  removeCoupon: () => Promise<CartResponse>;
  estimateShipping: (districtId: string) => Promise<CartResponse>;
  requestOtp: (phone: string) => Promise<OtpChallenge>;
  verifyOtp: (input: OtpVerification) => Promise<SessionResponse>;
  loginWithEmail: (input: EmailLogin) => Promise<SessionResponse>;
  logout: () => Promise<void>;
  getDivisions: (signal?: AbortSignal) => Promise<GeoOption[]>;
  getDistricts: (divisionId: string, signal?: AbortSignal) => Promise<GeoOption[]>;
  getUpazilas: (districtId: string, signal?: AbortSignal) => Promise<GeoOption[]>;
  createQuote: (input: CheckoutQuoteRequest) => Promise<CheckoutQuoteResponse>;
  placeOrder: (input: PlaceOrderRequest, idempotencyKey: string) => Promise<PlaceOrderResponse>;
  getOrder: (number: string, signal?: AbortSignal) => Promise<OrderReceipt>;
  trackOrder: (input: TrackOrderRequest) => Promise<TrackingResponse>;
  clearMutationError: () => void;
};

const CommerceContext = createContext<CommerceContextValue | null>(null);

function commerceError(error: unknown): CommerceError {
  return error instanceof CommerceError
    ? error
    : new CommerceError("Something interrupted this request. Please try again.");
}

export function CommerceProvider({
  children,
  locale,
  client,
  autoBootstrap = true,
  initialSnapshot,
}: {
  children: ReactNode;
  locale: AppLocale;
  client?: CommerceApi;
  autoBootstrap?: boolean;
  initialSnapshot?: Partial<CommerceSnapshot>;
}) {
  const hasInitialSnapshot =
    initialSnapshot?.session !== undefined && initialSnapshot?.cart !== undefined;
  const startsBootstrapping = autoBootstrap && !hasInitialSnapshot;
  const [api] = useState<CommerceApi>(() => client ?? new CommerceClient());
  const [session, setSession] = useState<SessionResponse | null>(initialSnapshot?.session ?? null);
  const [cart, setCart] = useState<CartResponse | null>(initialSnapshot?.cart ?? null);
  const [csrf, setCsrf] = useState<string | null>(
    initialSnapshot?.session?.csrf_token ?? initialSnapshot?.cart?.csrf_token ?? null,
  );
  const [pendingAction, setPendingAction] = useState<PendingAction>(
    startsBootstrapping ? "bootstrap" : null,
  );
  const [isBootstrapping, setIsBootstrapping] = useState(startsBootstrapping);
  const [isReady, setIsReady] = useState(!startsBootstrapping);
  const [isCartMutating, setIsCartMutating] = useState(false);
  const [errors, setErrors] = useState<CommerceErrors>({
    session: null,
    cart: null,
    cartMutation: null,
    auth: null,
    checkout: null,
  });
  const bootstrapPromiseRef = useRef<Promise<void> | null>(null);
  const readyRef = useRef(!startsBootstrapping);
  const cartRef = useRef<CartResponse | null>(initialSnapshot?.cart ?? null);
  const cartEpochRef = useRef(0);
  const mutationQueueRef = useRef<Promise<void>>(Promise.resolve());
  const queuedMutationsRef = useRef(0);

  useEffect(() => {
    api.setCsrfListener(setCsrf);
    const initialCsrf = initialSnapshot?.session?.csrf_token ?? initialSnapshot?.cart?.csrf_token;
    if (initialCsrf) api.setCsrfToken(initialCsrf);
  }, [api, initialSnapshot?.cart?.csrf_token, initialSnapshot?.session?.csrf_token]);

  const acceptSession = useCallback(
    (nextSession: SessionResponse) => {
      setSession(nextSession);
      setCsrf(nextSession.csrf_token);
      api.setCsrfToken(nextSession.csrf_token);
      setErrors((current) => ({ ...current, session: null }));
      return nextSession;
    },
    [api],
  );

  const markReady = useCallback((ready: boolean) => {
    readyRef.current = ready;
    setIsReady(ready);
  }, []);

  const acceptCart = useCallback(
    (nextCart: CartResponse, epoch = cartEpochRef.current) => {
      const current = cartRef.current;
      if (epoch !== cartEpochRef.current) return current ?? nextCart;
      if (current && current.cart_id === nextCart.cart_id && nextCart.version < current.version) {
        return current;
      }
      cartRef.current = nextCart;
      setCart(nextCart);
      setCsrf(nextCart.csrf_token);
      api.setCsrfToken(nextCart.csrf_token);
      setErrors((current) => ({ ...current, cart: null, cartMutation: null }));
      return nextCart;
    },
    [api],
  );

  const bootstrap = useCallback(() => {
    if (bootstrapPromiseRef.current) return bootstrapPromiseRef.current;
    const epoch = cartEpochRef.current;
    setIsBootstrapping(true);
    setPendingAction("bootstrap");
    markReady(false);
    let cartLoaded = false;
    const task = (async () => {
      try {
        acceptSession(await api.session());
      } catch (error) {
        setErrors((current) => ({ ...current, session: commerceError(error) }));
      }
      try {
        acceptCart(await api.cart(locale), epoch);
        cartLoaded = epoch === cartEpochRef.current;
      } catch (error) {
        setErrors((current) => ({ ...current, cart: commerceError(error) }));
      }
    })();
    const tracked = task.finally(() => {
      if (bootstrapPromiseRef.current === tracked) bootstrapPromiseRef.current = null;
      const ready = cartLoaded || cartRef.current !== null;
      markReady(ready);
      setIsBootstrapping(false);
      setPendingAction((current) => (current === "bootstrap" ? null : current));
    });
    bootstrapPromiseRef.current = tracked;
    return tracked;
  }, [acceptCart, acceptSession, api, locale, markReady]);

  useEffect(() => {
    if (!autoBootstrap || readyRef.current) return;
    void bootstrap();
  }, [autoBootstrap, bootstrap]);

  useEffect(() => {
    if (!session?.can_refresh) return;
    const expiresAt = session.access_expires_at
      ? Date.parse(session.access_expires_at)
      : Date.now();
    const delay = session.authenticated
      ? Math.max(0, expiresAt - Date.now() - ACCESS_REFRESH_WINDOW_MS)
      : 0;
    const timer = window.setTimeout(() => {
      api
        .session()
        .then(acceptSession)
        .catch((error: unknown) => {
          setErrors((current) => ({ ...current, session: commerceError(error) }));
        });
    }, delay);
    return () => window.clearTimeout(timer);
  }, [acceptSession, api, session]);

  const ensureReady = useCallback(async () => {
    if (readyRef.current) return;
    await bootstrap();
    if (!readyRef.current) {
      throw new CommerceError("Commerce is not ready.", { code: "COMMERCE_NOT_READY" });
    }
  }, [bootstrap]);

  const refreshCart = useCallback(async () => {
    if (bootstrapPromiseRef.current) await bootstrapPromiseRef.current;
    await mutationQueueRef.current;
    const epoch = cartEpochRef.current;
    try {
      const accepted = acceptCart(await api.cart(locale), epoch);
      markReady(true);
      return accepted;
    } catch (error) {
      const normalized = commerceError(error);
      setErrors((current) => ({ ...current, cart: normalized }));
      throw normalized;
    }
  }, [acceptCart, api, locale, markReady]);

  const runCartMutation = useCallback(
    (
      action: Exclude<PendingAction, "bootstrap" | "auth" | "checkout" | null>,
      request: () => Promise<CartResponse>,
    ) => {
      queuedMutationsRef.current += 1;
      setIsCartMutating(true);
      setErrors((current) => ({ ...current, cartMutation: null }));
      const result = mutationQueueRef.current
        .catch(() => undefined)
        .then(async () => {
          await ensureReady();
          setPendingAction(action);
          const epoch = cartEpochRef.current;
          try {
            return acceptCart(await request(), epoch);
          } catch (error) {
            const normalized = commerceError(error);
            setErrors((current) => ({ ...current, cartMutation: normalized }));
            throw normalized;
          }
        });
      mutationQueueRef.current = result.then(
        () => undefined,
        () => undefined,
      );
      return result.finally(() => {
        queuedMutationsRef.current -= 1;
        if (queuedMutationsRef.current === 0) {
          setIsCartMutating(false);
          setPendingAction((current) =>
            current === "cart" || current === "coupon" || current === "shipping" ? null : current,
          );
        }
      });
    },
    [acceptCart, ensureReady],
  );

  const addItem = useCallback(
    (variantId: string, quantity: number) =>
      runCartMutation("cart", () => api.addCartItem({ variant_id: variantId, quantity }, locale)),
    [api, locale, runCartMutation],
  );
  const updateItem = useCallback(
    (itemId: string, quantity: number) =>
      runCartMutation("cart", () => api.updateCartItem(itemId, { quantity }, locale)),
    [api, locale, runCartMutation],
  );
  const removeItem = useCallback(
    (itemId: string) => runCartMutation("cart", () => api.removeCartItem(itemId, locale)),
    [api, locale, runCartMutation],
  );
  const applyCoupon = useCallback(
    (code: string) => runCartMutation("coupon", () => api.applyCartCoupon({ code }, locale)),
    [api, locale, runCartMutation],
  );
  const removeCoupon = useCallback(
    () => runCartMutation("coupon", () => api.removeCartCoupon(locale)),
    [api, locale, runCartMutation],
  );
  const estimateShipping = useCallback(
    (districtId: string) =>
      runCartMutation("shipping", () =>
        api.estimateCartShipping({ district_id: districtId }, locale),
      ),
    [api, locale, runCartMutation],
  );

  const completeLogin = useCallback(
    async (request: () => Promise<SessionResponse>) => {
      await mutationQueueRef.current;
      setPendingAction("auth");
      setErrors((current) => ({ ...current, auth: null }));
      try {
        const nextSession = acceptSession(await request());
        cartEpochRef.current += 1;
        await refreshCart();
        return nextSession;
      } catch (error) {
        const normalized = commerceError(error);
        setErrors((current) => ({ ...current, auth: normalized }));
        throw normalized;
      } finally {
        setPendingAction(null);
      }
    },
    [acceptSession, refreshCart],
  );

  const requestOtp = useCallback(
    async (phone: string) => {
      setPendingAction("auth");
      setErrors((current) => ({ ...current, auth: null }));
      try {
        return await api.requestOtp({ phone });
      } catch (error) {
        const normalized = commerceError(error);
        setErrors((current) => ({ ...current, auth: normalized }));
        throw normalized;
      } finally {
        setPendingAction(null);
      }
    },
    [api],
  );
  const verifyOtp = useCallback(
    (input: OtpVerification) => completeLogin(() => api.verifyOtp(input)),
    [api, completeLogin],
  );
  const loginWithEmail = useCallback(
    (input: EmailLogin) => completeLogin(() => api.loginWithEmail(input)),
    [api, completeLogin],
  );
  const logout = useCallback(async () => {
    await mutationQueueRef.current;
    setPendingAction("auth");
    setErrors((current) => ({ ...current, auth: null }));
    try {
      await api.logout();
      const nextSession = await api.session();
      acceptSession(nextSession);
      cartEpochRef.current += 1;
      await refreshCart();
    } catch (error) {
      const normalized = commerceError(error);
      setErrors((current) => ({ ...current, auth: normalized }));
      throw normalized;
    } finally {
      setPendingAction(null);
    }
  }, [acceptSession, api, refreshCart]);
  const getDivisions = useCallback(
    (signal?: AbortSignal) => api.divisions(locale, signal),
    [api, locale],
  );
  const getDistricts = useCallback(
    (divisionId: string, signal?: AbortSignal) => api.districts(divisionId, locale, signal),
    [api, locale],
  );
  const getUpazilas = useCallback(
    (districtId: string, signal?: AbortSignal) => api.upazilas(districtId, locale, signal),
    [api, locale],
  );
  const createQuote = useCallback(
    async (input: CheckoutQuoteRequest) => {
      await ensureReady();
      await mutationQueueRef.current;
      setPendingAction("checkout");
      setErrors((current) => ({ ...current, checkout: null }));
      try {
        const epoch = cartEpochRef.current;
        const quote = await api.quote(input, locale);
        acceptCart(quote.cart, epoch);
        return quote;
      } catch (error) {
        const normalized = commerceError(error);
        setErrors((current) => ({ ...current, checkout: normalized }));
        throw normalized;
      } finally {
        setPendingAction(null);
      }
    },
    [acceptCart, api, ensureReady, locale],
  );
  const placeOrder = useCallback(
    async (input: PlaceOrderRequest, idempotencyKey: string) => {
      await ensureReady();
      await mutationQueueRef.current;
      setPendingAction("checkout");
      setErrors((current) => ({ ...current, checkout: null }));
      try {
        const result = await api.placeOrder(input, idempotencyKey, locale);
        cartEpochRef.current += 1;
        void refreshCart().catch(() => undefined);
        return result;
      } catch (error) {
        const normalized = commerceError(error);
        setErrors((current) => ({ ...current, checkout: normalized }));
        throw normalized;
      } finally {
        setPendingAction(null);
      }
    },
    [api, ensureReady, locale, refreshCart],
  );
  const getOrder = useCallback(
    (number: string, signal?: AbortSignal) => api.order(number, locale, signal),
    [api, locale],
  );
  const trackOrder = useCallback(
    (input: TrackOrderRequest) => api.track(input, locale),
    [api, locale],
  );
  const clearMutationError = useCallback(
    () =>
      setErrors((current) => ({
        ...current,
        cartMutation: null,
        auth: null,
        checkout: null,
      })),
    [],
  );

  const value = useMemo<CommerceContextValue>(
    () => ({
      locale,
      session,
      cart,
      csrf,
      count: cart?.item_count ?? 0,
      isLoading: isBootstrapping || isCartMutating || pendingAction !== null,
      isBootstrapping,
      isReady,
      isCartMutating,
      pendingAction,
      errors,
      bootstrap,
      refreshCart,
      addItem,
      updateItem,
      removeItem,
      applyCoupon,
      removeCoupon,
      estimateShipping,
      requestOtp,
      verifyOtp,
      loginWithEmail,
      logout,
      getDivisions,
      getDistricts,
      getUpazilas,
      createQuote,
      placeOrder,
      getOrder,
      trackOrder,
      clearMutationError,
    }),
    [
      addItem,
      applyCoupon,
      bootstrap,
      cart,
      clearMutationError,
      createQuote,
      csrf,
      errors,
      estimateShipping,
      getDistricts,
      getDivisions,
      getOrder,
      getUpazilas,
      isBootstrapping,
      isCartMutating,
      isReady,
      loginWithEmail,
      locale,
      logout,
      pendingAction,
      placeOrder,
      refreshCart,
      removeCoupon,
      removeItem,
      requestOtp,
      session,
      trackOrder,
      updateItem,
      verifyOtp,
    ],
  );

  return <CommerceContext value={value}>{children}</CommerceContext>;
}

export function useCommerce(): CommerceContextValue {
  const value = use(CommerceContext);
  if (!value) throw new Error("useCommerce must be used inside CommerceProvider");
  return value;
}
