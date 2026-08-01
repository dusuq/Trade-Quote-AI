class CustomerProperty {
  final String id;
  final String addressLine1;
  final String city;
  final String state;
  final String zipCode;
  final String propertyType;

  CustomerProperty({
    required this.id,
    required this.addressLine1,
    required this.city,
    required this.state,
    required this.zipCode,
    required this.propertyType,
  });

  factory CustomerProperty.fromJson(Map<String, dynamic> json) {
    return CustomerProperty(
      id: json['id'] as String,
      addressLine1: json['address_line1'] as String? ?? '',
      city: json['city'] as String? ?? '',
      state: json['state'] as String? ?? '',
      zipCode: json['zip_code'] as String? ?? '',
      propertyType: json['property_type'] as String? ?? '',
    );
  }
}

class CustomerContact {
  final String id;
  final String name;
  final String email;
  final String phone;
  final String role;

  CustomerContact({
    required this.id,
    required this.name,
    required this.email,
    required this.phone,
    required this.role,
  });

  factory CustomerContact.fromJson(Map<String, dynamic> json) {
    return CustomerContact(
      id: json['id'] as String,
      name: json['name'] as String? ?? '',
      email: json['email'] as String? ?? '',
      phone: json['phone'] as String? ?? '',
      role: json['role'] as String? ?? '',
    );
  }
}

class Customer {
  final String id;
  final String tenantId;
  final String name;
  final String companyName;
  final String phone;
  final String email;
  final String status;
  final List<String> tags;
  final List<CustomerProperty> properties;
  final List<CustomerContact> contacts;

  Customer({
    required this.id,
    required this.tenantId,
    required this.name,
    required this.companyName,
    required this.phone,
    required this.email,
    required this.status,
    required this.tags,
    required this.properties,
    required this.contacts,
  });

  factory Customer.fromJson(Map<String, dynamic> json) {
    return Customer(
      id: json['id'] as String,
      tenantId: json['tenant_id'] as String? ?? '',
      name: json['display_name'] as String? ?? json['name'] as String? ?? '',
      companyName: json['company_name'] as String? ?? '',
      phone: json['phone'] as String? ?? '',
      email: json['email'] as String? ?? '',
      status: json['status'] as String? ?? 'active',
      tags: (json['tags'] as List?)?.cast<String>() ?? [],
      properties: (json['properties'] as List?)
              ?.map((p) => CustomerProperty.fromJson(p as Map<String, dynamic>))
              .toList() ??
          [],
      contacts: (json['contacts'] as List?)
              ?.map((c) => CustomerContact.fromJson(c as Map<String, dynamic>))
              .toList() ??
          [],
    );
  }
}
