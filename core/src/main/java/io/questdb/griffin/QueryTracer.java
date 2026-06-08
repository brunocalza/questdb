/*+*****************************************************************************
 *     ___                  _   ____  ____
 *    / _ \ _   _  ___  ___| |_|  _ \| __ )
 *   | | | | | | |/ _ \/ __| __| | | |  _ \
 *   | |_| | |_| |  __/\__ \ |_| |_| | |_) |
 *    \__\_\\__,_|\___||___/\__|____/|____/
 *
 *  Copyright (c) 2014-2019 Appsicle
 *  Copyright (c) 2019-2026 QuestDB
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at
 *
 *  http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 *
 ******************************************************************************/

package io.questdb.griffin;

public final class QueryTracer {

    private static final ThreadLocal<int[]> DEPTH = ThreadLocal.withInitial(() -> new int[]{0});
    private static volatile boolean ENABLED = Boolean.getBoolean("questdb.tracer.enabled");

    private QueryTracer() {
    }

    public static void enter(String where) {
        if (!ENABLED) return;
        enterImpl(where, null);
    }

    public static void enter(String where, String detail) {
        if (!ENABLED) return;
        enterImpl(where, detail);
    }

    public static void event(String where, String detail) {
        if (!ENABLED) return;
        int[] d = DEPTH.get();
        printLine(d[0], '.', where, detail);
    }

    public static void exit(String where) {
        if (!ENABLED) return;
        int[] d = DEPTH.get();
        if (d[0] > 0) {
            d[0]--;
        }
        printLine(d[0], '<', where, null);
    }

    public static boolean isEnabled() {
        return ENABLED;
    }

    public static void setEnabled(boolean enabled) {
        ENABLED = enabled;
    }

    private static void enterImpl(String where, String detail) {
        int[] d = DEPTH.get();
        printLine(d[0], '>', where, detail);
        d[0]++;
    }

    private static void printLine(int depth, char marker, String where, String detail) {
        StringBuilder sb = new StringBuilder(128);
        sb.append('[').append(Thread.currentThread().getName()).append("] ");
        sb.repeat("  ", Math.max(0, depth));
        sb.append(marker).append(' ').append(where);
        if (detail != null) {
            sb.append("  [").append(detail).append(']');
        }
        // Use System.err.println so output goes to stderr and stays out of QuestDB's log writers.
        // PrintStream.println is internally synchronized so concurrent worker threads won't interleave a line.
        System.err.println(sb);
    }
}
