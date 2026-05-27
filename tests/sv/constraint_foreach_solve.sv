// ============================================================
// constraint_foreach_solve.sv
// 测试 foreach 和 solve...before 约束模式
// ============================================================

package foreach_solve_pkg;

  // ----------------------------------------------------------
  // 1. foreach 基础
  // ----------------------------------------------------------
  class foreach_basic;
    rand bit [7:0] data[4];

    constraint c_foreach {
      foreach (data[i]) data[i] inside {[0:100]};
    }
  endclass

  // ----------------------------------------------------------
  // 2. foreach + 条件
  // ----------------------------------------------------------
  class foreach_conditional;
    rand bit [7:0] arr[4];
    rand bit       mode;

    constraint c_foreach_if {
      if (mode == 0)
        foreach (arr[i]) arr[i] inside {[0:127]};
      else
        foreach (arr[i]) arr[i] inside {[128:255]};
    }
  endclass

  // ----------------------------------------------------------
  // 3. foreach + 元素间关系
  // ----------------------------------------------------------
  class foreach_relation;
    rand int arr[4];

    constraint c_ordering {
      foreach (arr[i])
        if (i > 0) arr[i] > arr[i-1];
    }
  endclass

  // ----------------------------------------------------------
  // 4. solve...before
  // ----------------------------------------------------------
  class solve_before_basic;
    rand bit [2:0] sel;
    rand bit [7:0] data;

    constraint c_order { solve sel before data; }
    constraint c_sel   { sel inside {[0:7]}; }
    constraint c_data  { data inside {[0:255]}; }
  endclass

  // ----------------------------------------------------------
  // 5. solve...before + 条件
  // ----------------------------------------------------------
  class solve_before_cond;
    rand bit mode;
    rand bit [7:0] a;
    rand bit [7:0] b;

    constraint c_solve { solve mode before a; solve mode before b; }
    constraint c_mode {
      if (mode == 0) {
        a inside {[0:127]};
        b == a;
      } else {
        a inside {[128:255]};
        b == 255 - a;
      }
    }
  endclass

  // ----------------------------------------------------------
  // 6. foreach + solve before + 继承
  // ----------------------------------------------------------
  class base_array;
    rand int vals[3];

    constraint c_base {
      foreach (vals[i]) vals[i] >= 0;
      solve vals[0] before vals[1];
    }
  endclass

  class derived_array extends base_array;
    constraint c_derived {
      foreach (vals[i]) vals[i] <= 100;
      vals[0] < vals[1];
      vals[1] < vals[2];
    }
  endclass

  // ----------------------------------------------------------
  // 7. 动态数组 foreach
  // ----------------------------------------------------------
  class dyn_foreach;
    rand bit [7:0] dyn_arr[];

    constraint c_size {
      dyn_arr.size() inside {[2:8]};
    }

    constraint c_elems {
      foreach (dyn_arr[i]) dyn_arr[i] == i * 2;
    }
  endclass

  // ----------------------------------------------------------
  // 8. foreach + sum
  // ----------------------------------------------------------
  class foreach_sum;
    rand int items[4];

    constraint c_sum {
      foreach (items[i]) items[i] inside {[0:100]};
      items.sum() with (int'(item)) < 256;
    }
  endclass

  // ----------------------------------------------------------
  // 9. 多维 foreach
  // ----------------------------------------------------------
  class multi_dim;
    rand bit [7:0] matrix[2][3];

    constraint c_matrix {
      foreach (matrix[i,j])
        matrix[i][j] inside {[0:50]};
    }
  endclass

  // ----------------------------------------------------------
  // 10. 组合: 包含 foreach 的类实例
  // ----------------------------------------------------------
  class foreach_env;
    rand foreach_basic  fb;
    rand solve_before_basic sb;
    rand bit [7:0] global_ctrl;

    constraint c_env {
      global_ctrl inside {8'h00, 8'h01};
    }
  endclass

endpackage
