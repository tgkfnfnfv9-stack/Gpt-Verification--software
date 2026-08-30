package org.phase9;

/** Positive startup check used only by the build-only preflight workflow. */
public final class RuntimeClassOriginGuardSelfTest {
    private RuntimeClassOriginGuardSelfTest() {}

    public static void main(String[] args) throws Exception {
        RuntimeClassOriginGuard.assertActive();
        Class.forName("com.dukascopy.api.system.TesterFactory");
        System.out.println("class_origin_guard_self_test=PASS");
    }
}
