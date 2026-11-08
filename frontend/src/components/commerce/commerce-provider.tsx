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
  SessionUser,
  TrackOrderRequest,
  TrackingResponse,
} from "@/lib/commerce/types";
import type {
  CheckoutPaymentMethodsResponse,
  CustomerPaymentAttempt,
  PaymentAttemptCreateResponse,
  PaymentProvider,
} from "@/lib/providers/types";

type PendingAction =
  "bootstrap" | "cart" | "auth" | "coupon" | "shipping" | "checkout" | "payment" | null;
type ResourceStatus = "idle" | "loading" | "ready" | "error";

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
  isSessionReady: boolean;
  isCartMutating: boolean;
  sessionStatus: ResourceStatus;
  cartStatus: ResourceStatus;
  pendingAction: PendingAction;
  errors: CommerceErrors;
  bootstrap: () => Promise<void>;
  refreshSession: () => Promise<SessionResponse>;
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
  patchSessionUser: (patch: Partial<Pick<SessionUser, "name" | "phone" | "email">>) => void;
  getDivisions: (signal?: AbortSignal) => Promise<GeoOption[]>;
  getDistricts: (divisionId: string, signal?: AbortSignal) => Promise<GeoOption[]>;
  getUpazilas: (districtId: string, signal?: AbortSignal) => Promise<GeoOption[]>;
  getPaymentMethods: (signal?: AbortSignal) => Promise<CheckoutPaymentMethodsResponse>;
  createQuote: (input: CheckoutQuoteRequest) => Promise<CheckoutQuoteResponse>;
  placeOrder: (input: PlaceOrderRequest, idempotencyKey: string) => Promise<PlaceOrderResponse>;
  initiatePayment: (
    number: string,
    provider: PaymentProvider,
    idempotencyKey: string,
  ) => Promise<PaymentAttemptCreateResponse>;
  getLatestPaymentAttempt: (
    number: string,
    signal?: AbortSignal,
  ) => Promise<CustomerPaymentAttempt>;
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

function sessionPrincipal(session: SessionResponse | null): string {
  return session?.authenticated && session.user ? `user:${session.user.id}` : "guest";
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
  const hasInitialSession = initialSnapshot?.session !== undefined;
  const hasInitialCart = initialSnapshot?.cart !== undefined;
  const hasInitialSnapshot = hasInitialSession && hasInitialCart;
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
  const [isReady, setIsReady] = useState(hasInitialCart);
  const [sessionStatus, setSessionStatus] = useState<ResourceStatus>(
    hasInitialSession ? "ready" : startsBootstrapping ? "loading" : "idle",
  );
  const [cartStatus, setCartStatus] = useState<ResourceStatus>(
    hasInitialCart ? "ready" : startsBootstrapping ? "loading" : "idle",
  );
  const [isCartMutating, setIsCartMutating] = useState(false);
  const [errors, setErrors] = useState<CommerceErrors>({
    session: null,
    cart: null,
    cartMutation: null,
    auth: null,
    checkout: null,
  });
  const bootstrapPromiseRef = useRef<Promise<void> | null>(null);
  const readyRef = useRef(hasInitialCart);
  const cartRef = useRef<CartResponse | null>(initialSnapshot?.cart ?? null);
  const sessionRef = useRef<SessionResponse | null>(initialSnapshot?.session ?? null);
  const acceptedSessionRef = useRef(hasInitialSession);
  const cartEpochRef = useRef(0);
  const mutationQueueRef = useRef<Promise<void>>(Promise.resolve());
  const queuedMutationsRef = useRef(0);

  const markReady = useCallback((ready: boolean) => {
    readyRef.current = ready;
    setIsReady(ready);
  }, []);

  const acceptCart = useCallback(
    (nextCart: CartResponse, epoch = cartEpochRef.current) => {
      const current = cartRef.current;
      if (epoch !== cartEpochRef.current) {
        throw new CommerceError("The signed-in account changed.", {
          status: 409,
          code: "SESSION_PRINCIPAL_CHANGED",
        });
      }
      if (current && current.cart_id === nextCart.cart_id && nextCart.version < current.version) {
        return current;
      }
      cartRef.current = nextCart;
      setCart(nextCart);
      setCsrf(nextCart.csrf_token);
      api.setCsrfToken(nextCart.csrf_token);
      setErrors((current) => ({ ...current, cart: null, cartMutation: null }));
      setCartStatus("ready");
      return nextCart;
    },
    [api],
  );

  const commitSession = useCallback(
    (nextSession: SessionResponse) => {
      sessionRef.current = nextSession;
      setSession(nextSession);
      setCsrf(nextSession.csrf_token || null);
      api.setCsrfToken(nextSession.csrf_token || null);
      setErrors((current) => ({ ...current, session: null }));
      setSessionStatus("ready");
      return nextSession;
    },
    [api],
  );

  const loadCartForPrincipal = useCallback(
    async (epoch: number) => {
      await mutationQueueRef.current.catch(() => undefined);
      try {
        const accepted = acceptCart(await api.cart(locale), epoch);
        if (epoch === cartEpochRef.current) markReady(true);
        return accepted;
      } catch (error) {
        if (epoch === cartEpochRef.current) {
          setCartStatus("error");
          markReady(false);
          setErrors((current) => ({ ...current, cart: commerceError(error) }));
        }
        throw error;
      }
    },
    [acceptCart, api, locale, markReady],
  );

  const acceptSession = useCallback(
    (nextSession: SessionResponse) => {
      const previousPrincipal = sessionPrincipal(sessionRef.current);
      const nextPrincipal = sessionPrincipal(nextSession);
      const changed = acceptedSessionRef.current && previousPrincipal !== nextPrincipal;
      acceptedSessionRef.current = true;
      commitSession(nextSession);
      if (changed) {
        const epoch = ++cartEpochRef.current;
        cartRef.current = null;
        setCart(null);
        setCartStatus("loading");
        markReady(false);
        setErrors((current) => ({ ...current, cart: null, cartMutation: null }));
        void loadCartForPrincipal(epoch).catch(() => undefined);
      }
      return nextSession;
    },
    [commitSession, loadCartForPrincipal, markReady],
  );

  useEffect(() => {
    api.setCsrfListener(setCsrf);
    api.setSessionListener(acceptSession);
    const initialCsrf = initialSnapshot?.session?.csrf_token ?? initialSnapshot?.cart?.csrf_token;
    if (initialCsrf) api.setCsrfToken(initialCsrf);
  }, [acceptSession, api, initialSnapshot?.cart?.csrf_token, initialSnapshot?.session?.csrf_token]);

  const refreshSession = useCallback(async () => {
    setSessionStatus("loading");
    setErrors((current) => ({ ...current, session: null }));
    try {
      return acceptSession(await api.session());
    } catch (error) {
      const normalized = commerceError(error);
      if (normalized.code === "SESSION_PRINCIPAL_CHANGED" && sessionRef.current) {
        return sessionRef.current;
      }
      setSessionStatus("error");
      setErrors((current) => ({ ...current, session: normalized }));
      throw normalized;
    }
  }, [acceptSession, api]);

  const bootstrap = useCallback(() => {
    if (bootstrapPromiseRef.current) return bootstrapPromiseRef.current;
    const epoch = cartEpochRef.current;
    setIsBootstrapping(true);
    setPendingAction("bootstrap");
    setCartStatus("loading");
    if (!hasInitialCart) markReady(false);
    let cartLoaded = false;
    const task = (async () => {
      try {
        await refreshSession();
      } catch {}
      try {
        acceptCart(await api.cart(locale), epoch);
        cartLoaded = epoch === cartEpochRef.current;
      } catch (error) {
        if (epoch === cartEpochRef.current) {
          setCartStatus("error");
          setErrors((current) => ({ ...current, cart: commerceError(error) }));
        }
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
  }, [acceptCart, api, hasInitialCart, locale, markReady, refreshSession]);

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
          const normalized = commerceError(error);
          if (normalized.code === "SESSION_PRINCIPAL_CHANGED") return;
          setSessionStatus("error");
          setErrors((current) => ({ ...current, session: normalized }));
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
      if (epoch === cartEpochRef.current) {
        setCartStatus("error");
        if (!cartRef.current) markReady(false);
        setErrors((current) => ({ ...current, cart: normalized }));
      }
      throw normalized;
    }
  }, [acceptCart, api, locale, markReady]);

  const runCartMutation = useCallback(
    (
      action: Exclude<PendingAction, "bootstrap" | "auth" | "checkout" | "payment" | null>,
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
            if (epoch === cartEpochRef.current) {
              setErrors((current) => ({ ...current, cartMutation: normalized }));
            }
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
        return acceptSession(await request());
      } catch (error) {
        const normalized = commerceError(error);
        setErrors((current) => ({ ...current, auth: normalized }));
        throw normalized;
      } finally {
        setPendingAction(null);
      }
    },
    [acceptSession],
  );

  const requestOtp = useCallback(
    async (phone: string) => {
      setPendingAction("auth");
      setErrors((current) => ({ ...current, auth: null }));
      try {
        return await api.requestOtp({ phone, locale });
      } catch (error) {
        const normalized = commerceError(error);
        setErrors((current) => ({ ...current, auth: normalized }));
        throw normalized;
      } finally {
        setPendingAction(null);
      }
    },
    [api, locale],
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
    setPendingAction("auth");
    setErrors((current) => ({ ...current, auth: null }));
    try {
      await api.logout();
      acceptSession({
        authenticated: false,
        user: null,
        can_refresh: false,
        access_expires_at: null,
        csrf_token: "",
        merge_warnings: [],
      });
    } catch (error) {
      const normalized = commerceError(error);
      setErrors((current) => ({ ...current, auth: normalized }));
      throw normalized;
    } finally {
      setPendingAction(null);
    }
  }, [acceptSession, api]);

  const patchSessionUser = useCallback(
    (patch: Partial<Pick<SessionUser, "name" | "phone" | "email">>) => {
      const current = sessionRef.current;
      if (!current?.authenticated || !current.user) return;
      commitSession({ ...current, user: { ...current.user, ...patch } });
    },
    [commitSession],
  );
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
  const getPaymentMethods = useCallback(
    (signal?: AbortSignal) => api.paymentMethods(signal),
    [api],
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
        if (!result.payment_required) {
          cartEpochRef.current += 1;
          void refreshCart().catch(() => undefined);
        }
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
  const initiatePayment = useCallback(
    async (number: string, provider: PaymentProvider, idempotencyKey: string) => {
      setPendingAction("payment");
      setErrors((current) => ({ ...current, checkout: null }));
      try {
        return await api.initiatePayment(number, { provider }, idempotencyKey);
      } catch (error) {
        const normalized = commerceError(error);
        setErrors((current) => ({ ...current, checkout: normalized }));
        throw normalized;
      } finally {
        setPendingAction(null);
      }
    },
    [api],
  );
  const getLatestPaymentAttempt = useCallback(
    (number: string, signal?: AbortSignal) => api.latestPaymentAttempt(number, signal),
    [api],
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
      isSessionReady: sessionStatus === "ready",
      isCartMutating,
      sessionStatus,
      cartStatus,
      pendingAction,
      errors,
      bootstrap,
      refreshSession,
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
      patchSessionUser,
      getDivisions,
      getDistricts,
      getUpazilas,
      getPaymentMethods,
      createQuote,
      placeOrder,
      initiatePayment,
      getLatestPaymentAttempt,
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
      getLatestPaymentAttempt,
      getOrder,
      getPaymentMethods,
      getUpazilas,
      isBootstrapping,
      isCartMutating,
      isReady,
      sessionStatus,
      cartStatus,
      loginWithEmail,
      locale,
      logout,
      patchSessionUser,
      pendingAction,
      placeOrder,
      initiatePayment,
      refreshCart,
      refreshSession,
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
