// ============================================================
// constraint_edge.sv
// navisv constraint graph 功能测试 - 边界场景
// ============================================================

package constraint_edge_pkg;

  // ----------------------------------------------------------
  // 1. 无约束的 rand 变量
  // ----------------------------------------------------------
  class unconstrained_cls;
    rand bit [7:0] free_var;
    rand bit [7:0] bounded_var;

    constraint c_bounded {
      bounded_var inside {[0:100]};
    }
  endclass

  // ----------------------------------------------------------
  // 2. 空 constraint（只有注释）
  // ----------------------------------------------------------
  class empty_constraint_cls;
    rand bit [7:0] data;

    constraint c_empty {
      // this constraint is intentionally empty
      data inside {[0:255]};
    }
  endclass

  // ----------------------------------------------------------
  // 3. 同名 constraint 覆盖（子类覆盖父类）
  // ----------------------------------------------------------
  class parent_cls;
    rand bit [7:0] value;

    constraint c_val {
      value inside {[0:63]};
    }
  endclass

  class child_cls extends parent_cls;
    // 覆盖父类的 c_val
    constraint c_val {
      value inside {[64:127]};
    }
  endclass

  // ----------------------------------------------------------
  // 4. 多个 constraint 引用同一变量
  // ----------------------------------------------------------
  class multi_constraint_cls;
    rand bit [7:0] shared_var;
    rand bit [7:0] other;

    constraint c_multi_a {
      shared_var inside {[0:127]};
    }

    constraint c_multi_b {
      shared_var > other;
    }

    constraint c_multi_c {
      shared_var[7] == 1'b0;
    }
  endclass

  // ----------------------------------------------------------
  // 5. 深层继承链 (4 层)
  // ----------------------------------------------------------
  class level0;
    rand bit [7:0] deep_var;

    constraint c_l0 {
      deep_var inside {[0:255]};
    }
  endclass

  class level1 extends level0;
    constraint c_l1 {
      deep_var inside {[0:127]};
    }
  endclass

  class level2 extends level1;
    constraint c_l2 {
      deep_var inside {[0:63]};
    }
  endclass

  class level3 extends level2;
    rand bit [3:0] extra;

    constraint c_l3 {
      deep_var inside {[0:31]};
      extra < 4'h8;
    }
  endclass

  // ----------------------------------------------------------
  // 6. 多重组合（一个类包含多个不同类的实例）
  // ----------------------------------------------------------
  class comp_a;
    rand bit [7:0] x;
    constraint c_a { x inside {[0:50]}; }
  endclass

  class comp_b;
    rand bit [7:0] y;
    constraint c_b { y inside {[51:100]}; }
  endclass

  class multi_comp;
    rand comp_a inst_a;
    rand comp_b inst_b;
    rand bit [7:0] total;

    constraint c_total {
      total == inst_a.x + inst_b.y;
    }
  endclass

endpackage
