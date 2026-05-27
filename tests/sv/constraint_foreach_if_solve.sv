// ============================================================
// constraint_foreach_if_solve.sv
// 测试 foreach 里有 if、solve...before、复杂组合
// ============================================================

package foreach_if_solve_pkg;

  // ----------------------------------------------------------
  // 1. foreach 里有 if (基础)
  // ----------------------------------------------------------
  class foreach_if_basic;
    rand bit [7:0] data[4];
    rand bit       mode;

    constraint c_foreach_if {
      foreach (data[i])
        if (mode == 0)
          data[i] inside {[0:127]};
        else
          data[i] inside {[128:255]};
    }
  endclass

  // ----------------------------------------------------------
  // 2. foreach 里有 if + 索引相关条件
  // ----------------------------------------------------------
  class foreach_if_index;
    rand int arr[4];

    constraint c_order {
      foreach (arr[i])
        if (i > 0)
          arr[i] > arr[i-1];
    }
  endclass

  // ----------------------------------------------------------
  // 3. foreach 里有嵌套 if
  // ----------------------------------------------------------
  class foreach_nested_if;
    rand bit [7:0] data[4];
    rand bit [1:0] sel;

    constraint c_nested {
      foreach (data[i])
        if (sel == 0)
          data[i] == 0;
        else if (sel == 1)
          data[i] inside {[1:100]};
        else
          data[i] inside {[101:255]};
    }
  endclass

  // ----------------------------------------------------------
  // 4. foreach + if + 跨变量约束
  // ----------------------------------------------------------
  class foreach_if_cross;
    rand bit [7:0] src[4];
    rand bit [7:0] dst[4];
    rand bit       enable;

    constraint c_cross {
      foreach (src[i])
        if (enable)
          dst[i] == src[i];
        else
          dst[i] == 8'h00;
    }
  endclass

  // ----------------------------------------------------------
  // 5. solve...before + foreach + if
  // ----------------------------------------------------------
  class solve_foreach_if;
    rand bit [1:0] mode;
    rand bit [7:0] data[4];

    constraint c_solve { solve mode before data; }

    constraint c_mode_data {
      foreach (data[i])
        if (mode == 0)
          data[i] inside {[0:63]};
        else if (mode == 1)
          data[i] inside {[64:127]};
        else
          data[i] inside {[128:255]};
    }
  endclass

  // ----------------------------------------------------------
  // 6. 多个 foreach + if 约束
  // ----------------------------------------------------------
  class multi_foreach;
    rand bit [7:0] a[3];
    rand bit [7:0] b[3];
    rand bit       flag;

    constraint c_a {
      foreach (a[i])
        if (flag) a[i] > 100;
        else      a[i] <= 100;
    }

    constraint c_b {
      foreach (b[i])
        if (flag) b[i] == a[i];
        else      b[i] == 8'hFF - a[i];
    }
  endclass

  // ----------------------------------------------------------
  // 7. foreach + if + 继承
  // ----------------------------------------------------------
  class base_foreach;
    rand int vals[3];

    constraint c_base {
      foreach (vals[i])
        if (i == 0)
          vals[i] == 0;
        else
          vals[i] > vals[i-1];
    }
  endclass

  class derived_foreach extends base_foreach;
    constraint c_ext {
      foreach (vals[i])
        vals[i] < 1000;
    }
  endclass

  // ----------------------------------------------------------
  // 8. foreach + if + 组合
  // ----------------------------------------------------------
  class inner_pkt;
    rand bit [7:0] payload[4];
    rand bit       compressed;

    constraint c_payload {
      foreach (payload[i])
        if (compressed)
          payload[i] inside {[0:127]};
        else
          payload[i] inside {[0:255]};
    }
  endclass

  class outer_env;
    rand inner_pkt pkt;
    rand bit [7:0] header;

    constraint c_wrap {
      foreach (pkt.payload[i])
        pkt.payload[i] > header;
    }
  endclass

endpackage
