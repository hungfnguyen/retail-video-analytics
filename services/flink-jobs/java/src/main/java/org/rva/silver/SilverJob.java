package org.rva.silver;

/**
 * Compatibility shim.
 *
 * New deployments should use {@link SilverRealtimeJob} as the explicit entrypoint.
 * This class remains only so older manual commands or historical references do not
 * break immediately during the transition.
 */
public class SilverJob {
    public static void main(String[] args) throws Exception {
        SilverRealtimeJob.main(args);
    }
}
