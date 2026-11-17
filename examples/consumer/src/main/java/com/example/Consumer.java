package com.example;

import com.google.common.collect.ImmutableList;

public final class Consumer {
  private Consumer() {}

  public static ImmutableList<String> names() {
    return ImmutableList.of("offline", "maven");
  }
}
